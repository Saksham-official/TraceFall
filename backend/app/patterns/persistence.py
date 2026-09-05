"""Storing pattern findings.

`false_positive_note` is a NOT NULL column, so a finding that lost its note on the way
here fails the insert. That is deliberate — FR-66 is enforced twice, once by the registry
and once by the database.
"""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import addresses as addresses_repo
from app.db.models.blockchain import Address, Chain
from app.db.models.enums import ChainCode
from app.db.models.finding import PatternFinding
from app.patterns.base import Finding, StageResult

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
    ids = await addresses_repo.ids_for(session, chain, addresses)

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


async def load(
    session: AsyncSession, analysis_run_id: uuid.UUID, chain: ChainCode
) -> list[Finding]:
    """Stored findings, back as the value object the risk engine already speaks."""
    rows = await session.execute(
        select(PatternFinding, Address.address)
        .join(Address, Address.id == PatternFinding.subject_address_id)
        .join(Chain, Chain.id == Address.chain_id)
        .where(PatternFinding.analysis_run_id == analysis_run_id, Chain.code == chain)
    )
    return [
        Finding(
            pattern_type=row.pattern_type,
            severity=row.severity,
            subject_address=address,
            explanation=row.explanation,
            trigger_tx_hashes=list(row.trigger_tx_hashes),
            metrics=dict(row.metrics),
            false_positive_note=row.false_positive_note,
            detector_version=row.detector_version,
        )
        for row, address in rows
    ]
