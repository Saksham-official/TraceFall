"""Attribution orchestration and persistence.

Gathers the two inputs the decision procedure needs — dataset labels and behavioural
features — decides, and writes one `attributions` row per address. The tier rule is
enforced by a database CHECK constraint, so a bug here that collapsed the tiers would
fail the insert rather than reach an investigator.

**The chained inference is resolved in two passes, not by recursion.** An address that
looks like a deposit address is only as attributable as the address it sweeps to, so
sweep destinations are decided first, from their dataset labels and their own behaviour,
and those results are then fed back in. Destinations are decided without a destination of
their own — one link, deliberately. Recursing would let A→B→A loop, and would stack
inference on inference until a confidence number meant nothing.
"""

import logging
import uuid
from collections.abc import Sequence
from fractions import Fraction

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.attribution.decision import ENGINE_VERSION, AttributionResult, decide
from app.db import addresses as addresses_repo
from app.db.models.blockchain import Address
from app.db.models.entity import Attribution, Entity
from app.db.models.enums import AttributionTier, ChainCode
from app.intel import service as intel
from app.labels import matcher

log = logging.getLogger(__name__)


async def attribute(
    session: AsyncSession,
    chain: ChainCode,
    addresses: Sequence[str],
    asset_key: str | None = None,
) -> dict[str, AttributionResult]:
    """Decide every address, resolving sweep destinations first."""
    wanted = list(dict.fromkeys(addresses))
    if not wanted:
        return {}

    features = await intel.build_profiles(session, chain, wanted, asset_key)

    # Pass one: every address a subject sweeps to, decided on its own merits.
    #
    # Destinations inside the traced set are resolved here too. Skipping them because
    # they will be decided in pass two anyway looks like an optimisation and is a bug: a
    # deposit address whose exchange is *also* in the trace — the common case, since the
    # trace followed the money there — would lose its chained inference and report "a
    # deposit address for an unidentified service" while the exchange sat one hop away,
    # confirmed.
    destinations = {
        f.dominant_out_destination for f in features.values() if f.dominant_out_destination
    }
    outside = sorted(destinations - set(wanted))
    destination_features = await intel.build_profiles(session, chain, outside, asset_key)
    known_features = {**features, **destination_features}
    labels = await matcher.labels_for(session, chain, wanted + outside)
    resolved = {
        address: decide(address, labels.get(address), known_features.get(address))
        for address in sorted(destinations)
    }

    # Pass two: the subjects, now able to say which service they sweep into.
    results: dict[str, AttributionResult] = {}
    for address in wanted:
        feature = features.get(address)
        destination = feature.dominant_out_destination if feature else None
        results[address] = decide(
            address,
            labels.get(address),
            feature,
            destination=resolved.get(destination) if destination else None,
        )
    return results


async def persist(
    session: AsyncSession,
    analysis_run_id: uuid.UUID,
    chain: ChainCode,
    results: dict[str, AttributionResult],
) -> int:
    """Store the findings for one analysis run.

    Caveats are written into the evidence array rather than a separate column: they are
    part of what the investigator must read, and a caveat in a column nobody selects is a
    caveat nobody sees.
    """
    if not results:
        return 0

    address_ids = await addresses_repo.ids_for(session, chain, set(results))
    rows = []
    for address, result in results.items():
        evidence = list(result.evidence)
        evidence += [{"type": "CAVEAT", "detail": caveat} for caveat in result.caveats]
        if result.reason:
            evidence.append({"type": "REASON", "detail": result.reason})
        rows.append(
            Attribution(
                analysis_run_id=analysis_run_id,
                address_id=address_ids[address],
                entity_id=result.entity_id,
                entity_type=result.entity_type,
                tier=result.tier,
                confidence=result.confidence_decimal,
                method=result.method,
                evidence=evidence,
                engine_version=ENGINE_VERSION,
            )
        )
    session.add_all(rows)
    await session.commit()

    tiers = {tier: 0 for tier in AttributionTier}
    for result in results.values():
        tiers[result.tier] += 1
    log.info(
        "attributed %d addresses on %s: %s", len(rows), chain, {str(k): v for k, v in tiers.items()}
    )
    return len(rows)


async def load(session: AsyncSession, analysis_run_id: uuid.UUID) -> dict[str, AttributionResult]:
    """Stored attributions, back as the value object every consumer already speaks."""
    rows = await session.execute(
        select(Attribution, Address.address, Entity.name)
        .join(Address, Address.id == Attribution.address_id)
        .outerjoin(Entity, Entity.id == Attribution.entity_id)
        .where(Attribution.analysis_run_id == analysis_run_id)
    )
    return {
        address: AttributionResult(
            tier=row.tier,
            entity_type=row.entity_type,
            method=row.method,
            entity_id=row.entity_id,
            entity_name=entity_name,
            confidence=(
                Fraction(row.confidence).limit_denominator(10**12)
                if row.confidence is not None
                else None
            ),
            evidence=row.evidence,
        )
        for row, address, entity_name in rows
    }


class ServiceBoundaryChecker:
    """The callback the tracing engine takes to know where to stop.

    Tracing past an exchange hot wallet follows other customers' money, so the trace must
    stop there. Only a `CONFIRMED` service stops it — stopping on a guess would truncate
    the answer silently, which is the one thing the product must never do.

    Answers are cached because a trace revisits the same hub many times.
    """

    def __init__(self, session: AsyncSession, chain: ChainCode) -> None:
        self._session = session
        self._chain = chain
        self._cache: dict[str, bool] = {}

    async def __call__(self, address: str) -> bool:
        if address not in self._cache:
            labels = await matcher.labels_for(self._session, self._chain, [address])
            result = decide(address, labels.get(address), features=None)
            self._cache[address] = result.is_service
        return self._cache[address]
