"""Curated label datasets: parse, validate, ingest.

A label is only worth as much as its provenance, so every dataset file carries its source
name, URL, licence and date, and those land in `label_sources` before any label row is
written. `CONFIRMED` means "a named, dated source says so" — without this table it would
mean nothing (VASP_IDENTIFICATION.md section 3).

Every address is validated against its chain before ingestion. This is not defensive
politeness: the best available public TRON label source was measured at a 6% invalid
address rate (docs/research/OQ-08-tron-label-coverage.md section 4), and a malformed
address that reaches the database is a label that can never match anything.

Invalid rows are rejected and reported, never silently dropped.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.chains import registry
from app.chains.base import InvalidAddressError
from app.db.models.blockchain import Address, Chain
from app.db.models.entity import AddressLabel, Entity, LabelSource
from app.db.models.enums import ChainCode, EntityType, LabelReliability

log = logging.getLogger(__name__)


class SourceSpec(BaseModel):
    """Provenance. Every field here appears in the evidence an investigator reads."""

    name: str = Field(min_length=3, max_length=200)
    url: str | None = Field(default=None, max_length=500)
    licence: str = Field(min_length=3, max_length=200)
    reliability: LabelReliability
    dataset_date: date
    description: str | None = None


class LabelSpec(BaseModel):
    chain: ChainCode
    address: str = Field(min_length=1, max_length=64)
    entity: str = Field(min_length=1, max_length=200)
    entity_type: EntityType
    label_text: str = Field(min_length=1, max_length=300)
    label_type: str | None = Field(default=None, max_length=64)
    # `display` is regenerated from the canonical form on read, so it is accepted and
    # ignored — it exists in the files to make them reviewable by eye.
    display: str | None = None


class LabelFile(BaseModel):
    source: SourceSpec
    labels: list[LabelSpec]


@dataclass
class IngestSummary:
    source: str
    entities_written: int = 0
    addresses_written: int = 0
    labels_written: int = 0
    rejected: list[tuple[str, str]] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "source": self.source,
            "entities": self.entities_written,
            "addresses": self.addresses_written,
            "labels": self.labels_written,
            "rejected": len(self.rejected),
        }


def load_file(path: Path) -> LabelFile:
    """Parse and structurally validate one dataset file.

    Raises `ValidationError` with the offending field, which is more use than a
    half-ingested dataset.
    """
    return LabelFile.model_validate(json.loads(path.read_text()))


async def ingest_file(session: AsyncSession, path: Path) -> IngestSummary:
    return await ingest(session, load_file(path))


async def ingest_directory(session: AsyncSession, directory: Path) -> list[IngestSummary]:
    """Ingest every dataset in a directory, in a stable order."""
    summaries = []
    for path in sorted(directory.glob("*.json")):
        try:
            summaries.append(await ingest_file(session, path))
        except (ValidationError, json.JSONDecodeError) as exc:
            log.error("label dataset %s is malformed and was not ingested: %s", path.name, exc)
            raise
    return summaries


async def ingest(session: AsyncSession, dataset: LabelFile) -> IngestSummary:
    """Write one dataset. Re-running it changes nothing.

    Idempotency comes from the unique constraints the database already holds, so this
    never has to check-then-insert — that version is a race, not an optimisation.
    """
    summary = IngestSummary(source=dataset.source.name)
    source_id = await _upsert_source(session, dataset.source)

    valid: list[tuple[LabelSpec, str]] = []
    for spec in dataset.labels:
        try:
            validated = registry.validate(spec.address, spec.chain)
        except InvalidAddressError as exc:
            summary.rejected.append((spec.address, str(exc)))
            continue
        if validated.chain is not spec.chain:
            summary.rejected.append(
                (spec.address, f"declared {spec.chain}, but the address is {validated.chain}")
            )
            continue
        valid.append((spec, validated.canonical))

    entities = await _upsert_entities(session, [spec for spec, _ in valid])
    summary.entities_written = len(entities)
    addresses = await _upsert_addresses(session, valid)
    summary.addresses_written = len(addresses)

    rows = [
        {
            "address_id": addresses[(spec.chain, canonical)],
            "entity_id": entities[(spec.entity, spec.entity_type)],
            "label_source_id": source_id,
            "label_text": spec.label_text,
            "label_type": spec.label_type,
        }
        for spec, canonical in valid
    ]
    if rows:
        result = await session.execute(
            insert(AddressLabel).values(rows).on_conflict_do_nothing().returning(AddressLabel.id)
        )
        summary.labels_written = len(result.all())
    await session.commit()

    log.info("ingested labels: %s", summary.as_dict())
    for address, reason in summary.rejected:
        log.warning("rejected label for %s: %s", address, reason)
    return summary


async def _upsert_source(session: AsyncSession, spec: SourceSpec) -> int:
    """Source metadata is refreshed on re-ingest — a dataset's date is the point of it."""
    values = {
        "name": spec.name,
        "url": spec.url,
        "licence": spec.licence,
        "description": spec.description,
        "reliability": spec.reliability,
        "dataset_date": spec.dataset_date,
    }
    statement = insert(LabelSource).values(values)
    source_id = await session.scalar(
        statement.on_conflict_do_update(
            index_elements=[LabelSource.name],
            set_={k: v for k, v in values.items() if k != "name"},
        ).returning(LabelSource.id)
    )
    assert source_id is not None
    return source_id


async def _upsert_entities(
    session: AsyncSession, specs: list[LabelSpec]
) -> dict[tuple[str, EntityType], int]:
    wanted = {(spec.entity, spec.entity_type) for spec in specs}
    if not wanted:
        return {}
    rows = [
        {
            "name": name,
            "entity_type": entity_type,
            "is_sanctioned": entity_type is EntityType.SANCTIONED,
        }
        for name, entity_type in sorted(wanted, key=lambda w: (w[0], str(w[1])))
    ]
    # Entities have no unique constraint — two venues may legitimately share a name
    # across types — so this is a read-then-insert of the ones that are missing.
    existing = await _existing_entities(session, wanted)
    missing = [row for row in rows if (row["name"], row["entity_type"]) not in existing]
    if missing:
        await session.execute(insert(Entity).values(missing))
        existing = await _existing_entities(session, wanted)
    return existing


async def _existing_entities(
    session: AsyncSession, wanted: set[tuple[str, EntityType]]
) -> dict[tuple[str, EntityType], int]:
    result = await session.execute(
        select(Entity.name, Entity.entity_type, Entity.id).where(
            Entity.name.in_({name for name, _ in wanted})
        )
    )
    return {
        (name, entity_type): entity_id
        for name, entity_type, entity_id in result
        if (name, entity_type) in wanted
    }


async def _upsert_addresses(
    session: AsyncSession, valid: list[tuple[LabelSpec, str]]
) -> dict[tuple[ChainCode, str], int]:
    chain_ids = {
        code: chain_id for code, chain_id in await session.execute(select(Chain.code, Chain.id))
    }
    wanted = {(spec.chain, canonical) for spec, canonical in valid}
    if not wanted:
        return {}

    await session.execute(
        insert(Address)
        .values(
            [
                {"chain_id": chain_ids[chain], "address": address}
                for chain, address in sorted(wanted, key=lambda w: (str(w[0]), w[1]))
            ]
        )
        .on_conflict_do_nothing(constraint="chain_id_address")
    )
    result = await session.execute(
        select(Chain.code, Address.address, Address.id)
        .join(Chain, Chain.id == Address.chain_id)
        .where(Address.address.in_({address for _, address in wanted}))
    )
    return {
        (code, address): row_id for code, address, row_id in result if (code, address) in wanted
    }
