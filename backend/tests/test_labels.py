"""Label ingestion and lookup.

`CONFIRMED` means "a named, dated source says so", so what is really under test here is
provenance: that a label cannot reach the database without its source, that a malformed
address is rejected loudly rather than stored as an unmatchable string, and that two
sources disagreeing stay two sources disagreeing.

The committed OFAC dataset is ingested as-is — it is real published data, and a test
against invented labels would not have caught the 6% invalid-address rate measured in the
best available public TRON source (OQ-08).
"""

import json
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.blockchain import Address
from app.db.models.entity import AddressLabel, Entity, LabelSource
from app.db.models.enums import ChainCode, EntityType, LabelReliability
from app.labels import loader, matcher

LABELS_DIR = Path(__file__).resolve().parents[2] / "data" / "labels"
OFAC_DATASET = LABELS_DIR / "ofac_sanctioned.json"

# Real TRON addresses: the USDT-TRC20 contract and an address confirmed in the OQ-08
# research to be a Binance cold wallet. Used here only as well-formed identifiers.
TRON_A = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
TRON_B = "TMuA6YqfCeX8EhbfYEg5y7S4DqzSJireY9"


def dataset(labels: list[dict[str, str]], name: str = "Test dataset") -> loader.LabelFile:
    return loader.LabelFile.model_validate(
        {
            "source": {
                "name": name,
                "url": "https://example.test/dataset",
                "licence": "CC0",
                "reliability": "MEDIUM",
                "dataset_date": "2026-07-01",
            },
            "labels": labels,
        }
    )


def exchange_label(address: str, entity: str = "Test Exchange") -> dict[str, str]:
    return {
        "chain": "TRON",
        "address": address,
        "entity": entity,
        "entity_type": "EXCHANGE",
        "label_text": f"{entity} hot wallet",
        "label_type": "EXCHANGE",
    }


# --- The committed dataset ----------------------------------------------------------


def test_the_committed_ofac_dataset_parses_and_carries_its_licence() -> None:
    parsed = loader.load_file(OFAC_DATASET)

    assert parsed.source.reliability is LabelReliability.HIGH
    assert "MIT" in parsed.source.licence
    assert parsed.source.url
    assert parsed.source.dataset_date <= date.today()
    assert len(parsed.labels) > 100
    assert {label.entity_type for label in parsed.labels} == {EntityType.SANCTIONED}


def test_the_committed_dataset_contains_no_malformed_address() -> None:
    """Every address survives its chain's checksum. This is the OQ-08 lesson, asserted."""
    summary_labels = loader.load_file(OFAC_DATASET).labels
    from app.chains import registry

    for label in summary_labels:
        validated = registry.validate(label.address, label.chain)
        assert validated.canonical == label.address


async def test_ingesting_the_real_dataset_stores_it_with_its_source(
    session: AsyncSession,
) -> None:
    summary = await loader.ingest_file(session, OFAC_DATASET)

    assert summary.rejected == []
    assert summary.labels_written > 100
    source = await session.scalar(
        select(LabelSource).where(LabelSource.name == "OFAC SDN digital currency addresses")
    )
    assert source is not None
    assert source.dataset_date is not None
    assert source.record_count is None or source.record_count >= 0
    assert source.reliability is LabelReliability.HIGH

    tron = await session.scalar(
        select(func.count())
        .select_from(AddressLabel)
        .join(Address, Address.id == AddressLabel.address_id)
        .where(Address.address.like("T%"))
    )
    assert tron and tron > 100


async def test_re_ingestion_is_a_no_op(session: AsyncSession) -> None:
    first = await loader.ingest_file(session, OFAC_DATASET)
    second = await loader.ingest_file(session, OFAC_DATASET)

    assert first.labels_written > 0
    assert second.labels_written == 0
    total = await session.scalar(select(func.count()).select_from(AddressLabel))
    assert total == first.labels_written


async def test_ingest_directory_loads_every_committed_dataset(session: AsyncSession) -> None:
    summaries = await loader.ingest_directory(session, LABELS_DIR)

    assert summaries
    assert all(summary.rejected == [] for summary in summaries)


# --- Validation ---------------------------------------------------------------------


async def test_a_malformed_address_is_rejected_not_stored(session: AsyncSession) -> None:
    """A bad checksum in a label file is a defect in the source, reported as one."""
    # TRON_B with one character changed: valid base58, wrong checksum.
    broken = TRON_B[:-1] + ("9" if TRON_B[-1] != "9" else "8")

    summary = await loader.ingest(session, dataset([exchange_label(broken)]))

    assert summary.labels_written == 0
    assert len(summary.rejected) == 1
    assert broken in summary.rejected[0][0]
    assert await session.scalar(select(func.count()).select_from(AddressLabel)) == 0


async def test_an_address_from_the_wrong_chain_is_rejected(session: AsyncSession) -> None:
    ethereum_address = "0x" + "ab" * 20
    summary = await loader.ingest(session, dataset([exchange_label(ethereum_address)]))

    assert summary.labels_written == 0
    assert len(summary.rejected) == 1


async def test_valid_rows_still_load_when_one_row_is_broken(session: AsyncSession) -> None:
    """A defective row costs its own label, not the whole dataset."""
    summary = await loader.ingest(
        session, dataset([exchange_label(TRON_A), exchange_label("Tnot-an-address")])
    )

    assert summary.labels_written == 1
    assert len(summary.rejected) == 1


def test_a_dataset_without_a_licence_will_not_parse(tmp_path: Path) -> None:
    """No dataset is ingested until its licence is confirmed and written down (OQ-07)."""
    path = tmp_path / "unlicensed.json"
    path.write_text(
        json.dumps(
            {
                "source": {
                    "name": "Somebody's scrape",
                    "reliability": "LOW",
                    "dataset_date": "2026-01-01",
                },
                "labels": [],
            }
        )
    )
    with pytest.raises(ValidationError):
        loader.load_file(path)


# --- Lookup -------------------------------------------------------------------------


async def test_lookup_returns_the_source_needed_to_cite_it(session: AsyncSession) -> None:
    await loader.ingest(session, dataset([exchange_label(TRON_A, "Binance")]))

    found = await matcher.labels_for(session, ChainCode.TRON, [TRON_A])

    assert set(found) == {TRON_A}
    match = found[TRON_A].matches[0]
    assert match.entity_name == "Binance"
    assert match.entity_type is EntityType.EXCHANGE
    assert match.source_name == "Test dataset"
    assert match.source_url == "https://example.test/dataset"
    assert match.dataset_date == date(2026, 7, 1)
    assert found[TRON_A].conflicted is False


async def test_an_unlabelled_address_is_simply_absent(session: AsyncSession) -> None:
    await loader.ingest(session, dataset([exchange_label(TRON_A)]))

    found = await matcher.labels_for(session, ChainCode.TRON, [TRON_A, TRON_B])

    assert set(found) == {TRON_A}


async def test_two_sources_naming_different_operators_are_both_kept(
    session: AsyncSession,
) -> None:
    """The MaskEX/UEEx case measured in OQ-08, which FR-75 exists for."""
    await loader.ingest(session, dataset([exchange_label(TRON_A, "MaskEX")], name="Source A"))
    await loader.ingest(session, dataset([exchange_label(TRON_A, "UEEx")], name="Source B"))

    found = await matcher.labels_for(session, ChainCode.TRON, [TRON_A])

    assert found[TRON_A].conflicted is True
    assert {m.entity_name for m in found[TRON_A].matches} == {"MaskEX", "UEEx"}
    assert {m.source_name for m in found[TRON_A].matches} == {"Source A", "Source B"}


async def test_the_same_entity_from_two_sources_is_not_a_conflict(
    session: AsyncSession,
) -> None:
    await loader.ingest(session, dataset([exchange_label(TRON_A, "Binance")], name="Source A"))
    await loader.ingest(session, dataset([exchange_label(TRON_A, "Binance")], name="Source B"))

    found = await matcher.labels_for(session, ChainCode.TRON, [TRON_A])

    assert found[TRON_A].conflicted is False
    assert len(found[TRON_A].matches) == 2
    assert await session.scalar(select(func.count()).select_from(Entity)) == 1


async def test_lookup_is_scoped_to_one_chain(session: AsyncSession) -> None:
    await loader.ingest(session, dataset([exchange_label(TRON_A)]))

    assert await matcher.labels_for(session, ChainCode.ETHEREUM, [TRON_A]) == {}


async def test_refreshing_a_dataset_updates_its_date(session: AsyncSession) -> None:
    """Datasets age, and the age is shown — so a re-ingest must move it."""
    await loader.ingest(session, dataset([exchange_label(TRON_A)]))
    refreshed = dataset([exchange_label(TRON_A)])
    refreshed.source.dataset_date = date(2026, 9, 1)
    await loader.ingest(session, refreshed)

    found = await matcher.labels_for(session, ChainCode.TRON, [TRON_A])

    assert found[TRON_A].matches[0].dataset_date == date(2026, 9, 1)
