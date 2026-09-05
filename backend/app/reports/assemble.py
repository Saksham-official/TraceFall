"""Gathering everything a report states, straight from the database.

**Every fact here is read, never re-derived.** The report must agree with what the API
showed the investigator, so it reads the stored rows rather than recomputing from the
trace — a report that disagrees with the screen it came from is worse than no report.

Narrative is templated, never model-written (ADR-021). Prose is more mechanical for it,
and every address, amount, hash and entity name comes from a row.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.analysis import AnalysisRun, Trace, TraceEdge, TraceNode
from app.db.models.blockchain import Address, Chain
from app.db.models.case import Case, CaseAddress
from app.db.models.entity import Attribution, Entity
from app.db.models.enums import AttributionTier, ChainCode, RiskBand
from app.db.models.finding import PatternFinding, RiskAssessment
from app.db.models.output import EvidenceItem
from app.db.models.user import User

# Printed on every report. Taken from LIMITATIONS.md section 13, the claims checklist.
DISCLAIMERS = [
    "This report is an investigative aid. It is not a forensic certification and is not "
    "court-admissible on its own.",
    "TraceFall does not and cannot identify the person behind an address. Attribution "
    "identifies services and datasets, never individuals.",
    "A risk score is an investigative prioritisation number. It is not a probability of "
    "fraud and not evidence of criminal conduct.",
    "An attribution marked PROBABLE is an inference from observed behaviour, not a "
    "confirmed fact. It must be verified before it is acted on.",
    "Analysis covers TRON and Ethereum only. Value that left through a swap, a bridge or "
    "a mixer is reported as reaching that point and no further.",
    "Absence of a finding is not evidence of absence. An address reported as "
    "UNATTRIBUTED is one public data cannot identify, not one shown to be innocent.",
]

TRACING_CONVENTION = (
    "Fund flow is attributed using the haircut model: value leaving an address is "
    "attributed to the victim in proportion to the tainted share of everything that "
    "address received. Tracing follows a single asset, stops at confirmed services, and "
    "records why every branch ended."
)


@dataclass
class ReportData:
    """Everything the renderers print. Assembled once, rendered to PDF, JSON or CSV."""

    case: dict[str, Any]
    address: dict[str, Any]
    run: dict[str, Any]
    summary: dict[str, Any]
    key_transactions: list[dict[str, Any]] = field(default_factory=list)
    attributions: list[dict[str, Any]] = field(default_factory=list)
    patterns: list[dict[str, Any]] = field(default_factory=list)
    risk: list[dict[str, Any]] = field(default_factory=list)
    sources: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    disclaimers: list[str] = field(default_factory=lambda: list(DISCLAIMERS))
    tracing_convention: str = TRACING_CONVENTION
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def as_dict(self) -> dict[str, Any]:
        return {
            "case": self.case,
            "address": self.address,
            "run": self.run,
            "summary": self.summary,
            "key_transactions": self.key_transactions,
            "attributions": self.attributions,
            "patterns": self.patterns,
            "risk": self.risk,
            "sources": self.sources,
            "evidence": self.evidence,
            "tracing_convention": self.tracing_convention,
            "disclaimers": self.disclaimers,
            "generated_at": self.generated_at.isoformat(),
        }


async def gather(session: AsyncSession, run_id: uuid.UUID) -> ReportData:
    run = await session.get(AnalysisRun, run_id)
    if run is None:
        raise ValueError(f"analysis run {run_id} does not exist")
    case = await session.get(Case, run.case_id)
    root = await session.get(Address, run.root_address_id)
    assert case is not None and root is not None
    chain = await session.get(Chain, root.chain_id)
    assert chain is not None
    owner = await session.get(User, case.owner_id)
    case_address = await session.scalar(
        select(CaseAddress).where(CaseAddress.case_id == case.id, CaseAddress.address_id == root.id)
    )

    names = {
        row_id: address
        for row_id, address in await session.execute(select(Address.id, Address.address))
    }
    trace = await session.scalar(
        select(Trace).where(Trace.analysis_run_id == run_id).order_by(Trace.computed_at.desc())
    )

    return ReportData(
        case={
            "case_number": case.case_number,
            "title": case.title,
            "status": str(case.status),
            "priority": str(case.priority),
            "ncrp_reference": case.ncrp_reference,
            "fir_reference": case.fir_reference,
            "incident_date": case.incident_date.isoformat() if case.incident_date else None,
            "reported_loss_inr": (
                str(case.reported_loss_inr) if case.reported_loss_inr is not None else None
            ),
            "owner": owner.full_name if owner else None,
            "created_at": case.created_at.isoformat(),
        },
        address={
            "address": root.address,
            "chain": str(chain.code),
            "explorer_url": chain.explorer_url_template.replace("{address}", root.address),
            "role": str(case_address.role) if case_address else None,
            "reported_amount": (
                str(case_address.reported_amount)
                if case_address and case_address.reported_amount is not None
                else None
            ),
            "reported_asset_symbol": case_address.reported_asset_symbol if case_address else None,
            "reported_at": (
                case_address.reported_at.isoformat()
                if case_address and case_address.reported_at
                else None
            ),
        },
        run={
            "id": str(run.id),
            "status": str(run.status),
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "engine_versions": _versions(run.engine_versions),
            "degradations": run.degradations,
            "parameters": run.params,
        },
        summary=await _summary(session, run, trace, names),
        key_transactions=await _key_transactions(session, trace, names),
        attributions=await _attributions(session, run_id),
        patterns=await _patterns(session, run_id, names),
        risk=await _risk(session, run_id, names),
        sources=await _sources(session, run_id),
        evidence=await _evidence_hashes(session, trace),
    )


def _raw(value: Any) -> str:
    """A raw amount as plain digits.

    `str()` on a NUMERIC comes back as `5.000E+7`, which is the wrong way to print a
    number that goes into a case file — an exact integer must look like one.
    """
    return "0" if value is None else str(int(value))


def _versions(engine_versions: dict[str, Any]) -> dict[str, Any]:
    """Only the version strings; the per-stage summaries are noise in a case file."""
    return {k: v for k, v in engine_versions.items() if isinstance(v, str)}


async def _summary(
    session: AsyncSession,
    run: AnalysisRun,
    trace: Trace | None,
    names: dict[int, str],
) -> dict[str, Any]:
    if trace is None:
        return {"traced": False, "note": "No trace was produced for this analysis."}

    nodes = (await session.scalars(select(TraceNode).where(TraceNode.trace_id == trace.id))).all()
    terminals = [n for n in nodes if n.is_terminal]
    return {
        "traced": True,
        "root_address": names.get(trace.root_address_id),
        "total_traced_raw": _raw(trace.total_traced_raw),
        "anchor_tx_hash": trace.anchor_tx_hash,
        "anchored": trace.anchor_tx_hash is not None,
        "max_depth": trace.max_depth,
        "node_count": trace.node_count,
        "edge_count": trace.edge_count,
        "taint_model": str(trace.taint_model),
        "termination_reasons": sorted(
            {str(n.termination_reason) for n in terminals if n.termination_reason}
        ),
        "terminal_addresses": [
            {
                "address": names.get(n.address_id),
                "reason": str(n.termination_reason) if n.termination_reason else None,
                "tainted_amount_raw": _raw(n.tainted_amount_raw),
            }
            for n in sorted(terminals, key=lambda n: -n.tainted_amount_raw)
        ],
        # Nothing is silently dropped: what the trace did not follow is part of the answer.
        "pruned_branches": len(trace.pruned),
        "unavailable_addresses": [u["address"] for u in trace.unavailable],
    }


async def _key_transactions(
    session: AsyncSession, trace: Trace | None, names: dict[int, str]
) -> list[dict[str, Any]]:
    """The highest-value flows, each with the hashes behind it."""
    if trace is None:
        return []
    edges = (await session.scalars(select(TraceEdge).where(TraceEdge.trace_id == trace.id))).all()
    return [
        {
            "from": names.get(e.from_address_id),
            "to": names.get(e.to_address_id),
            "total_amount_raw": _raw(e.total_amount_raw),
            "tainted_amount_raw": _raw(e.tainted_amount_raw),
            "transfer_count": e.transfer_count,
            "first_transfer_at": e.first_transfer_at.isoformat() if e.first_transfer_at else None,
            "last_transfer_at": e.last_transfer_at.isoformat() if e.last_transfer_at else None,
            "tx_hashes": list(e.tx_hashes),
        }
        for e in sorted(edges, key=lambda e: -e.tainted_amount_raw)
    ]


async def _attributions(session: AsyncSession, run_id: uuid.UUID) -> list[dict[str, Any]]:
    rows = await session.execute(
        select(Attribution, Address.address, Entity.name)
        .join(Address, Address.id == Attribution.address_id)
        .outerjoin(Entity, Entity.id == Attribution.entity_id)
        .where(Attribution.analysis_run_id == run_id)
        .order_by(Attribution.tier, Address.address)
    )
    return [
        {
            "address": address,
            # The tier is printed as its own word, never folded into the entity name.
            "tier": str(row.tier),
            "entity_name": entity_name,
            "entity_type": str(row.entity_type),
            "confidence": float(row.confidence) if row.confidence is not None else None,
            "method": str(row.method),
            "evidence": row.evidence,
        }
        for row, address, entity_name in rows
    ]


async def _patterns(
    session: AsyncSession, run_id: uuid.UUID, names: dict[int, str]
) -> list[dict[str, Any]]:
    rows = await session.execute(
        select(PatternFinding, Address.address)
        .join(Address, Address.id == PatternFinding.subject_address_id)
        .where(PatternFinding.analysis_run_id == run_id)
        .order_by(PatternFinding.severity.desc(), PatternFinding.pattern_type)
    )
    return [
        {
            "pattern_type": str(row.pattern_type),
            "severity": str(row.severity),
            "subject_address": address,
            "explanation": row.explanation,
            # Printed with every finding. A pattern without its false positives reads as
            # a conclusion, and this document is read by people who will act on it.
            "false_positive_note": row.false_positive_note,
            "trigger_tx_hashes": list(row.trigger_tx_hashes),
            "involved_addresses": [names[i] for i in row.involved_address_ids if i in names],
        }
        for row, address in rows
    ]


async def _risk(
    session: AsyncSession, run_id: uuid.UUID, names: dict[int, str]
) -> list[dict[str, Any]]:
    rows = await session.execute(
        select(RiskAssessment, Address.address)
        .join(Address, Address.id == RiskAssessment.address_id)
        .where(RiskAssessment.analysis_run_id == run_id)
        .order_by(RiskAssessment.score.desc())
    )
    return [
        {
            "address": address,
            "score": row.score,
            "band": str(row.band),
            "confidence": float(row.confidence),
            "config_version": row.config_version,
            "signals": [s for s in row.signals if s.get("points", 0) > 0],
            "not_evaluated": row.not_evaluated,
        }
        for row, address in rows
    ]


async def _sources(session: AsyncSession, run_id: uuid.UUID) -> list[dict[str, Any]]:
    """Which providers were called and when — the retrieval record (FR-113)."""
    rows = await session.scalars(select(EvidenceItem).where(EvidenceItem.analysis_run_id == run_id))
    by_provider: dict[str, dict[str, Any]] = {}
    for item in rows:
        provider = item.provider or "unknown"
        entry = by_provider.setdefault(
            provider,
            {
                "provider": provider,
                "requests": 0,
                "first": None,
                "last": None,
                "is_fixture": item.is_fixture,
            },
        )
        entry["requests"] += 1
        stamp = item.retrieved_at.isoformat()
        entry["first"] = min(entry["first"] or stamp, stamp)
        entry["last"] = max(entry["last"] or stamp, stamp)
    return sorted(by_provider.values(), key=lambda s: str(s["provider"]))


async def _evidence_hashes(session: AsyncSession, trace: Trace | None) -> list[dict[str, Any]]:
    """The appendix: every transaction hash the findings rest on, deduplicated."""
    if trace is None:
        return []
    edges = (await session.scalars(select(TraceEdge).where(TraceEdge.trace_id == trace.id))).all()
    seen: dict[str, dict[str, Any]] = {}
    for edge in edges:
        for tx_hash in edge.tx_hashes:
            seen.setdefault(tx_hash, {"tx_hash": tx_hash, "edges": 0})["edges"] += 1
    return sorted(seen.values(), key=lambda item: str(item["tx_hash"]))


def headline(data: ReportData) -> str:
    """One templated sentence naming the outcome. No model wrote this (ADR-021)."""
    confirmed = [
        a
        for a in data.attributions
        if a["tier"] == str(AttributionTier.CONFIRMED) and a["entity_name"]
    ]
    probable = [
        a
        for a in data.attributions
        if a["tier"] == str(AttributionTier.PROBABLE) and a["entity_name"]
    ]
    address = data.address["address"]

    if confirmed:
        names = ", ".join(sorted({str(a["entity_name"]) for a in confirmed}))
        return (
            f"Traced value from {address} reached {names}, confirmed by a named dataset. "
            f"A KYC or freeze request naming the addresses and hashes in this report may "
            f"identify the receiving account."
        )
    if probable:
        best = max(probable, key=lambda a: a["confidence"] or 0)
        return (
            f"Traced value from {address} probably reached {best['entity_name']} "
            f"({(best['confidence'] or 0) * 100:.0f}% confidence). This is an inference "
            f"from transaction behaviour, not a confirmed identification, and must be "
            f"verified before it is acted on."
        )
    return (
        f"No service could be reliably identified for the value traced from {address}. "
        f"Identifying the controller requires KYC records held by a VASP, or data sources "
        f"beyond public blockchain analytics."
    )


def risk_headline(data: ReportData) -> str:
    root = next((r for r in data.risk if r["address"] == data.address["address"]), None)
    if root is None:
        return "No risk assessment was produced for the suspect address."
    band = root["band"]
    detail = root["signals"][0]["description"] if root["signals"] else "No signal scored."
    urgency = (
        "Act now." if band == str(RiskBand.CRITICAL) else "Review alongside the evidence below."
    )
    return (
        f"The suspect address scored {root['score']} of 100 ({band}) at "
        f"{root['confidence']:.2f} confidence. Leading signal: {detail} {urgency}"
    )


__all__ = [
    "DISCLAIMERS",
    "TRACING_CONVENTION",
    "ChainCode",
    "ReportData",
    "gather",
    "headline",
    "risk_headline",
]
