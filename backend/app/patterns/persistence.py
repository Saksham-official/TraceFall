"""Storing pattern findings.

`false_positive_note` is a NOT NULL column, so a finding that lost its note on the way
here fails the insert. That is deliberate — FR-66 is enforced twice, once by the registry
and once by the database.
"""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.blockchain import Address, Chain
from app.db.models.enums import ChainCode
from app.db.models.finding import PatternFinding
from app.patterns.base import StageResult

log = logging.getLogger(__name__)


async def save(
    session: AsyncSession, analysis_run_id: uuid.UUID, chain: ChainCode, result: StageResult
) -> int:
    """Write the findings for one analysis run and return how many landed."""
    if not result.findings:
        return 0

    addresses = {finding.subject_address for finding in result.findings}
    for finding in result.findings:
        addresses.update(finding.involved_addresses)
    ids = await _address_ids(session, chain, addresses)

    rows = [
        PatternFinding(
            analysis_run_id=analysis_run_id,
            pattern_type=finding.pattern_type,
            severity=finding.severity,
            subject_address_id=ids[finding.subject_address],
            involved_address_ids=[
                ids[address] for address in finding.involved_addresses if address in ids
            ],
            trigger_tx_hashes=finding.trigger_tx_hashes,
            metrics=finding.metrics,
            explanation=finding.explanation,
            false_positive_note=finding.false_positive_note,
            detector_version=finding.detector_version,
        )
        for finding in result.findings
    ]
    session.add_all(rows)
    await session.commit()

    if result.degraded:
        log.warning("pattern stage degraded: %s", result.unavailable)
    log.info("stored %d pattern findings on %s", len(rows), chain)
    return len(rows)


async def _address_ids(
    session: AsyncSession, chain: ChainCode, addresses: set[str]
) -> dict[str, int]:
    chain_id = await session.scalar(select(Chain.id).where(Chain.code == chain))
    assert chain_id is not None
    await session.execute(
        insert(Address)
        .values([{"chain_id": chain_id, "address": address} for address in sorted(addresses)])
        .on_conflict_do_nothing(constraint="chain_id_address")
    )
    return {
        address: row_id
        for address, row_id in await session.execute(
            select(Address.address, Address.id).where(
                Address.chain_id == chain_id, Address.address.in_(addresses)
            )
        )
    }
