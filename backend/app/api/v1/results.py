"""Analysis results: the graph, the patterns, the attributions.

All three are derived on read from what the pipeline stored. The graph in particular is
rebuilt from the trace rather than kept as a second copy — it is cheap to build and a
cached copy that drifts from the trace it came from would be worse than useless.

Case isolation runs through `get_accessible_case` exactly as it does everywhere else: a
user who cannot see the case gets 404, never 403, so the endpoint leaks nothing about
whether the run exists (ADR-013).
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.attribution import engine as attribution
from app.core.deps import SessionDep, get_accessible_case, require_role
from app.core.exceptions import NotFound
from app.db.models.analysis import AnalysisRun
from app.db.models.blockchain import Address
from app.db.models.entity import Attribution, Entity
from app.db.models.enums import (
    AttributionTier,
    EntityType,
    PatternType,
    RiskBand,
    UserRole,
)
from app.db.models.finding import PatternFinding, RiskAssessment
from app.db.models.user import User
from app.graph import algorithms, builder, serialize
from app.risk.engine import DISCLAIMER
from app.tracing import persistence as trace_store

router = APIRouter(tags=["results"])

Investigator = Annotated[
    User, Depends(require_role(UserRole.ADMIN, UserRole.INVESTIGATOR, UserRole.ANALYST))
]

# Chokepoints worth naming in a report. Everything below this is noise on a small graph.
MIN_BETWEENNESS = 0.01
TOP_CHOKEPOINTS = 10


async def _run(run_id: uuid.UUID, user: User, session: SessionDep) -> AnalysisRun:
    run = await session.get(AnalysisRun, run_id)
    if run is None:
        raise NotFound("Analysis run not found")
    # Raises 404 for a case the user cannot reach, so this leaks nothing either.
    await get_accessible_case(run.case_id, user, session)
    return run


@router.get("/analyses/{run_id}/graph")
async def get_graph(
    run_id: uuid.UUID,
    user: Investigator,
    session: SessionDep,
    max_nodes: Annotated[int, Query(ge=1, le=5_000)] = serialize.DEFAULT_MAX_NODES,
    expand_node: str | None = None,
) -> dict[str, Any]:
    """Render-ready graph (FR-90..96).

    `truncated` is always present and the UI must show it: silently hiding half a fund
    flow from an investigator is unacceptable.
    """
    run = await _run(run_id, user, session)
    trace = await trace_store.load(session, run.id)
    if trace is None:
        raise NotFound("This analysis has no trace")

    graph = builder.enrich(builder.build(trace), await attribution.load(session, run.id))
    payload = (
        serialize.expand(graph, expand_node, max_nodes)
        if expand_node
        else serialize.render(graph, max_nodes)
    )
    payload["total_nodes"] = graph.number_of_nodes()
    payload["measures"] = _measures(graph)
    # The trace's own account of what it left out travels with the picture, not in a
    # separate call an investigator has to know to make.
    payload["pruned_branches"] = [
        {**branch, "tainted_amount_raw": str(branch["tainted_amount_raw"])}
        for branch in (
            {
                "from": b.from_address,
                "to": b.to_address,
                "reason": b.reason,
                "tainted_amount_raw": b.tainted_raw,
            }
            for b in trace.pruned
        )
    ]
    payload["unavailable_addresses"] = trace.unavailable
    return payload


def _measures(graph: builder.TraceGraph) -> dict[str, Any]:
    scores = algorithms.betweenness(graph)
    ranked = sorted(
        ((address, score) for address, score in scores.items() if score > MIN_BETWEENNESS),
        key=lambda item: (-item[1], item[0]),
    )[:TOP_CHOKEPOINTS]
    chokepoints = [
        {"address": address, "betweenness": round(score, 4)} for address, score in ranked
    ]
    main_flow = algorithms.highest_value_path(graph)
    return {
        "chokepoints": chokepoints,
        "components": len(algorithms.components(graph)),
        "cycles": algorithms.cycles(graph),
        "highest_value_path": main_flow.addresses if main_flow else [],
    }


@router.get("/analyses/{run_id}/attributions")
async def get_attributions(
    run_id: uuid.UUID,
    user: Investigator,
    session: SessionDep,
    tier: AttributionTier | None = None,
    entity_type: EntityType | None = None,
) -> list[dict[str, Any]]:
    """Every attribution in the run (FR-70..77), tier intact and evidence attached."""
    run = await _run(run_id, user, session)

    statement = (
        select(Attribution, Address.address, Entity.name)
        .join(Address, Address.id == Attribution.address_id)
        .outerjoin(Entity, Entity.id == Attribution.entity_id)
        .where(Attribution.analysis_run_id == run.id)
        .order_by(Attribution.tier, Address.address)
    )
    if tier is not None:
        statement = statement.where(Attribution.tier == tier)
    if entity_type is not None:
        statement = statement.where(Attribution.entity_type == entity_type)

    return [
        {
            "address": address,
            "tier": row.tier,
            "entity_name": entity_name,
            "entity_type": row.entity_type,
            # Never folded into the tier, and null for CONFIRMED — a confirmed claim is
            # not a probability.
            "confidence": float(row.confidence) if row.confidence is not None else None,
            "method": row.method,
            "evidence": row.evidence,
            "engine_version": row.engine_version,
            "computed_at": row.computed_at,
        }
        for row, address, entity_name in await session.execute(statement)
    ]


@router.get("/analyses/{run_id}/patterns")
async def get_patterns(
    run_id: uuid.UUID,
    user: Investigator,
    session: SessionDep,
    pattern_type: PatternType | None = None,
) -> list[dict[str, Any]]:
    """Detected patterns (FR-60..66).

    `false_positive_note` is returned on every finding. A pattern shown without what else
    produces its shape will be read as a conclusion.
    """
    run = await _run(run_id, user, session)

    statement = (
        select(PatternFinding, Address.address)
        .join(Address, Address.id == PatternFinding.subject_address_id)
        .where(PatternFinding.analysis_run_id == run.id)
        .order_by(PatternFinding.severity.desc(), PatternFinding.pattern_type)
    )
    if pattern_type is not None:
        statement = statement.where(PatternFinding.pattern_type == pattern_type)

    rows = list(await session.execute(statement))
    involved = {row_id for row, _ in rows for row_id in row.involved_address_ids}
    names = (
        {
            row_id: address
            for row_id, address in await session.execute(
                select(Address.id, Address.address).where(Address.id.in_(involved))
            )
        }
        if involved
        else {}
    )
    return [
        {
            "pattern_type": row.pattern_type,
            "severity": row.severity,
            "subject_address": address,
            "involved_addresses": [names[i] for i in row.involved_address_ids if i in names],
            "trigger_tx_hashes": row.trigger_tx_hashes,
            "metrics": row.metrics,
            "explanation": row.explanation,
            "false_positive_note": row.false_positive_note,
            "detector_version": row.detector_version,
        }
        for row, address in rows
    ]


@router.get("/analyses/{run_id}/risk")
async def get_risk(
    run_id: uuid.UUID,
    user: Investigator,
    session: SessionDep,
    band: RiskBand | None = None,
) -> dict[str, Any]:
    """Risk assessments (FR-80..86), root first.

    The breakdown is always returned. A score without its reasons is useless in exactly
    the moment it is questioned, and `not_evaluated` is kept separate from zero-scoring
    so "we did not check" never reads as "we checked and found nothing".
    """
    run = await _run(run_id, user, session)

    statement = (
        select(RiskAssessment, Address.address)
        .join(Address, Address.id == RiskAssessment.address_id)
        .where(RiskAssessment.analysis_run_id == run.id)
        .order_by(RiskAssessment.score.desc(), Address.address)
    )
    if band is not None:
        statement = statement.where(RiskAssessment.band == band)

    rows = [_assessment(row, address) for row, address in await session.execute(statement)]
    root_address = await session.scalar(
        select(Address.address).where(Address.id == run.root_address_id)
    )
    return {
        "root": next((r for r in rows if r["address"] == root_address), None),
        "nodes": rows,
        "disclaimer": DISCLAIMER,
    }


def _assessment(row: RiskAssessment, address: str) -> dict[str, Any]:
    return {
        "address": address,
        "score": row.score,
        "band": row.band,
        # Reported beside the score, never multiplied into it: "probably very bad on
        # partial data" and "thoroughly checked and fine" must not collapse (FR-83).
        "confidence": float(row.confidence),
        "signals": row.signals,
        "not_evaluated": row.not_evaluated,
        "config_version": row.config_version,
        "engine_version": row.engine_version,
        "computed_at": row.computed_at,
    }
