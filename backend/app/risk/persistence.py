"""Storing risk assessments, and raising the alerts they justify.

The `signals` array is NOT NULL and CHECK-constrained to be non-empty, so an assessment
that lost its breakdown fails the insert. A score without its reasons is useless in
exactly the moment it is questioned.
"""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.blockchain import Address, Chain
from app.db.models.entity import Attribution
from app.db.models.enums import (
    AlertType,
    AttributionTier,
    ChainCode,
    EntityType,
    RiskBand,
    Severity,
)
from app.db.models.finding import Alert, RiskAssessment
from app.risk.engine import Assessment

log = logging.getLogger(__name__)

# Bands that justify interrupting an investigator rather than waiting to be looked at.
ALERTING_BANDS = frozenset({RiskBand.CRITICAL})


async def save(
    session: AsyncSession,
    analysis_run_id: uuid.UUID,
    case_id: uuid.UUID,
    chain: ChainCode,
    assessments: dict[str, Assessment],
) -> int:
    if not assessments:
        return 0

    ids = await _address_ids(session, chain, set(assessments))
    rows = [
        RiskAssessment(
            analysis_run_id=analysis_run_id,
            address_id=ids[address],
            score=assessment.score,
            band=assessment.band,
            confidence=assessment.confidence_decimal,
            signals=[s.as_dict() for s in assessment.signals],
            not_evaluated=[n.as_dict() for n in assessment.not_evaluated],
            config_version=assessment.config_version,
            engine_version=assessment.engine_version,
        )
        for address, assessment in assessments.items()
    ]
    session.add_all(rows)
    await session.flush()
    alerts = await _alerts(session, analysis_run_id, case_id, ids, assessments)
    await session.commit()

    log.info("scored %d addresses on %s, %d alert(s) raised", len(rows), chain, alerts)
    return len(rows)


async def _alerts(
    session: AsyncSession,
    analysis_run_id: uuid.UUID,
    case_id: uuid.UUID,
    ids: dict[str, int],
    assessments: dict[str, Assessment],
) -> int:
    """Alerts fire on sanctioned contact, mixer contact, and a critical score (FR-100).

    Sanctions and mixer contact alert regardless of the score: those are dataset-matched
    facts an investigator must see immediately, not scores to be triaged.

    **Only a `CONFIRMED` match raises one.** A deposit address that funnels into a
    sanctioned entity is inferred to belong to that entity, and inheriting the entity type
    is correct — but an alert reading "this address is on a sanctions list" states an
    inference as a fact, which is the one thing this system must never do. A `PROBABLE`
    sanctions link still reaches the investigator: it is in the attribution, with its tier
    and its evidence, where the qualification travels with the claim.
    """
    attributions = {
        address: (entity_type, tier)
        for address, entity_type, tier in await session.execute(
            select(Address.address, Attribution.entity_type, Attribution.tier)
            .join(Attribution, Attribution.address_id == Address.id)
            .where(Attribution.analysis_run_id == analysis_run_id)
        )
    }

    raised = []
    for address, assessment in assessments.items():
        entity_type, tier = attributions.get(address, (None, None))
        if tier is not AttributionTier.CONFIRMED:
            entity_type = None
        if entity_type is EntityType.SANCTIONED:
            raised.append(
                (
                    AlertType.SANCTIONED_CONTACT,
                    Severity.HIGH,
                    address,
                    f"{address} is on a sanctions list and is part of this trace.",
                )
            )
        elif entity_type is EntityType.MIXER:
            raised.append(
                (
                    AlertType.MIXER_CONTACT,
                    Severity.HIGH,
                    address,
                    f"Traced value reached the mixer at {address}.",
                )
            )
        if assessment.band in ALERTING_BANDS:
            leading = assessment.signals[0].description if assessment.signals else ""
            raised.append(
                (
                    AlertType.CRITICAL_RISK,
                    Severity.HIGH,
                    address,
                    f"{address} scored {assessment.score} ({assessment.band}). {leading}",
                )
            )

    session.add_all(
        [
            Alert(
                case_id=case_id,
                analysis_run_id=analysis_run_id,
                alert_type=alert_type,
                severity=severity,
                address_id=ids[address],
                trigger_reason=reason,
                source_finding_type="RISK_ASSESSMENT",
            )
            for alert_type, severity, address, reason in raised
        ]
    )
    return len(raised)


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
