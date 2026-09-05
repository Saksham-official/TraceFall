"""The golden case — a regression lock on the numbers that reach a police report.

The whole pipeline runs against committed provider fixtures, offline, and **every number
it produces is compared against a stored expected value**. Any change to normalization,
tracing, attribution, patterns or risk that moves one of these numbers fails here.

That is the point. A refactor that quietly changes a taint amount, a confidence, or a risk
score is the failure this project cannot detect any other way — the pipeline would still
run, the report would still generate, and the number in it would be different.

**Updating the expectation is deliberate, never automatic.** Run with
`UPDATE_GOLDEN=1 pytest tests/test_golden_case.py` and commit the diff *with an
explanation of why the number changed*. If you cannot explain it, that is the bug.
"""

import json
import os
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import worker
from app.core.config import get_settings
from app.db.models.analysis import AnalysisRun, Trace, TraceEdge, TraceNode
from app.db.models.blockchain import Address, Chain
from app.db.models.case import Case, CaseAddress
from app.db.models.entity import Attribution, Entity
from app.db.models.enums import (
    AddressRole,
    AnalysisStatus,
    AttributionTier,
    ChainCode,
    ReportFormat,
)
from app.db.models.finding import Alert, PatternFinding, RiskAssessment
from app.db.models.user import User
from app.labels import loader
from app.reports import assemble, generator
from tests import golden_scenario as scenario
from tests.conftest import make_user

EXPECTED_PATH = Path(__file__).parent / "golden" / "expected.json"
UPDATING = os.environ.get("UPDATE_GOLDEN") == "1"


@pytest.fixture
async def golden_run(
    session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> uuid.UUID:
    """Run the entire pipeline over the golden fixtures and return the run id."""
    scenario.write_fixtures(tmp_path / "fixtures")
    monkeypatch.setattr(get_settings(), "fixture_path", str(tmp_path / "fixtures"))
    monkeypatch.setattr(get_settings(), "report_storage_path", str(tmp_path / "reports"))
    monkeypatch.setattr(get_settings(), "evidence_storage_path", str(tmp_path / "evidence"))

    # The exchange hot wallet is the one CONFIRMED label in the scenario. Everything
    # downstream of it — the deposit inference, the entity in the report headline — rests
    # on this single dataset match, which is exactly how the product is meant to work.
    await loader.ingest(
        session,
        loader.LabelFile.model_validate(
            {
                "source": {
                    "name": "Golden test dataset",
                    "url": "https://example.test/golden",
                    "licence": "CC0",
                    "reliability": "HIGH",
                    "dataset_date": "2026-07-01",
                },
                "labels": [
                    {
                        "chain": "TRON",
                        "address": scenario.HOT,
                        "entity": scenario.EXCHANGE_NAME,
                        "entity_type": "EXCHANGE",
                        "label_text": f"{scenario.EXCHANGE_NAME} hot wallet",
                    }
                ],
            }
        ),
    )

    user = await make_user(session, "golden@example.gov")
    chain = await session.scalar(select(Chain).where(Chain.code == ChainCode.TRON))
    assert chain is not None
    root = Address(chain_id=chain.id, address=scenario.SCAM)
    case = Case(case_number="TF-GOLDEN-0001", title="Golden case", owner_id=user.id)
    session.add_all([root, case])
    await session.flush()
    session.add(
        CaseAddress(
            case_id=case.id,
            address_id=root.id,
            role=AddressRole.SUSPECT,
            added_by=user.id,
            # Anchoring is part of what is locked: the trace must find the victim's
            # transfer among everything the address received.
            reported_amount=Decimal("40000"),
            reported_at=scenario.BASE,
        )
    )
    run = AnalysisRun(
        case_id=case.id,
        root_address_id=root.id,
        status=AnalysisStatus.QUEUED,
        triggered_by=user.id,
        params={"max_depth": 3, "time_window_days": 3650, "taint_threshold": 0.06},
    )
    session.add(run)
    await session.commit()

    await worker._run_pipeline(run.id)
    return run.id


async def observed(session: AsyncSession, run_id: uuid.UUID) -> dict[str, Any]:
    """Everything the golden case locks, in a stable, diffable shape."""
    run = await session.get(AnalysisRun, run_id)
    assert run is not None
    await session.refresh(run)

    names = {
        row_id: address
        for row_id, address in await session.execute(select(Address.id, Address.address))
    }
    label = {value: key for key, value in vars(scenario).items() if isinstance(value, str)}

    def named(address_id: int) -> str:
        """Report addresses by their scenario role, so a diff is readable."""
        return label.get(names[address_id], names[address_id])

    def rename(address: str) -> str:
        """The same, for the places that store an address rather than its row id."""
        return label.get(address, address)

    trace = await session.scalar(select(Trace).where(Trace.analysis_run_id == run_id))
    assert trace is not None
    nodes = (await session.scalars(select(TraceNode).where(TraceNode.trace_id == trace.id))).all()
    edges = (await session.scalars(select(TraceEdge).where(TraceEdge.trace_id == trace.id))).all()

    attributions = await session.execute(
        select(Attribution, Entity.name)
        .outerjoin(Entity, Entity.id == Attribution.entity_id)
        .where(Attribution.analysis_run_id == run_id)
    )
    patterns = (
        await session.scalars(
            select(PatternFinding).where(PatternFinding.analysis_run_id == run_id)
        )
    ).all()
    risk = (
        await session.scalars(
            select(RiskAssessment).where(RiskAssessment.analysis_run_id == run_id)
        )
    ).all()
    alerts = (await session.scalars(select(Alert).where(Alert.analysis_run_id == run_id))).all()

    report = await assemble.gather(session, run_id)

    return {
        "run": {"status": str(run.status), "degradations": len(run.degradations)},
        "trace": {
            "root": named(trace.root_address_id),
            "anchored": trace.anchor_tx_hash is not None,
            "anchor_tx_hash": trace.anchor_tx_hash,
            "total_traced_raw": str(int(trace.total_traced_raw or 0)),
            "node_count": trace.node_count,
            "edge_count": trace.edge_count,
            "pruned_branches": [
                {"from": rename(b["from"]), "to": rename(b["to"]), "reason": b["reason"]}
                for b in trace.pruned
            ],
            "unavailable": [
                {"address": u["address"], "reason": u["reason"]} for u in trace.unavailable
            ],
        },
        "nodes": sorted(
            (
                {
                    "address": named(n.address_id),
                    "depth": n.depth,
                    "tainted_amount_raw": str(int(n.tainted_amount_raw)),
                    "pruned_amount_raw": str(int(n.pruned_amount_raw)),
                    "is_terminal": n.is_terminal,
                    "termination_reason": str(n.termination_reason)
                    if n.termination_reason
                    else None,
                }
                for n in nodes
            ),
            key=lambda n: str(n["address"]),
        ),
        "edges": sorted(
            (
                {
                    "from": named(e.from_address_id),
                    "to": named(e.to_address_id),
                    "total_amount_raw": str(int(e.total_amount_raw)),
                    "tainted_amount_raw": str(int(e.tainted_amount_raw)),
                    "transfer_count": e.transfer_count,
                    "tx_hashes": sorted(e.tx_hashes),
                }
                for e in edges
            ),
            key=lambda e: (str(e["from"]), str(e["to"])),
        ),
        "attributions": sorted(
            (
                {
                    "address": named(row.address_id),
                    "tier": str(row.tier),
                    "entity": entity_name,
                    "entity_type": str(row.entity_type),
                    "confidence": None if row.confidence is None else float(row.confidence),
                    "method": str(row.method),
                    "evidence_count": len(row.evidence),
                }
                for row, entity_name in attributions
            ),
            key=lambda a: str(a["address"]),
        ),
        "patterns": sorted(
            (
                {
                    "type": str(p.pattern_type),
                    "severity": str(p.severity),
                    "subject": named(p.subject_address_id),
                    "metrics": p.metrics,
                }
                for p in patterns
            ),
            key=lambda p: (str(p["type"]), str(p["subject"])),
        ),
        "risk": sorted(
            (
                {
                    "address": named(r.address_id),
                    "score": r.score,
                    "band": str(r.band),
                    "confidence": round(float(r.confidence), 4),
                    "config_version": r.config_version,
                    "signals": sorted(
                        ({"name": s["name"], "points": s["points"]} for s in r.signals),
                        key=lambda s: str(s["name"]),
                    ),
                    "not_evaluated": sorted(n["name"] for n in r.not_evaluated),
                }
                for r in risk
            ),
            key=lambda r: str(r["address"]),
        ),
        "alerts": sorted(str(a.alert_type) for a in alerts),
        "report": {
            "headline": assemble.headline(report).replace(scenario.SCAM, "SCAM"),
            "risk_headline": assemble.risk_headline(report).replace(scenario.SCAM, "SCAM"),
            "evidence_hashes": len(report.evidence),
            "disclaimer_count": len(report.disclaimers),
        },
    }


async def test_the_golden_case_matches_its_committed_expectation(
    session: AsyncSession, golden_run: uuid.UUID
) -> None:
    """Every number, locked. See this module's docstring before updating it."""
    actual = await observed(session, golden_run)

    if UPDATING:
        EXPECTED_PATH.parent.mkdir(parents=True, exist_ok=True)
        EXPECTED_PATH.write_text(json.dumps(actual, indent=2, sort_keys=True) + "\n")
        pytest.skip("golden expectation rewritten; review and commit the diff")

    assert EXPECTED_PATH.exists(), "run UPDATE_GOLDEN=1 pytest tests/test_golden_case.py"
    expected = json.loads(EXPECTED_PATH.read_text())

    # Compared section by section: a whole-blob mismatch tells you nothing about which
    # engine moved, and this test exists to be read when it fails.
    for section in expected:
        assert actual[section] == expected[section], f"{section} changed"
    assert set(actual) == set(expected)


async def test_the_golden_case_answers_the_problem_statement(
    session: AsyncSession, golden_run: uuid.UUID
) -> None:
    """Beyond the numbers: the case must actually reach a named exchange."""
    actual = await observed(session, golden_run)

    confirmed = [a for a in actual["attributions"] if a["tier"] == str(AttributionTier.CONFIRMED)]
    assert [a["entity"] for a in confirmed] == [scenario.EXCHANGE_NAME]
    assert "confirmed by a named dataset" in actual["report"]["headline"]

    # The deposit address is inferred, never asserted, and carries its confidence.
    deposit = next(a for a in actual["attributions"] if a["address"] == "DEPOSIT")
    assert deposit["tier"] == str(AttributionTier.PROBABLE)
    assert deposit["entity"] == scenario.EXCHANGE_NAME
    assert 0 < (deposit["confidence"] or 0) <= 0.95


async def test_the_golden_case_balances(session: AsyncSession, golden_run: uuid.UUID) -> None:
    """The accounting invariant, re-checked from stored rows rather than from memory."""
    from app.tracing import invariants, persistence

    reloaded = await persistence.load(session, golden_run)

    assert reloaded is not None
    invariants.check(reloaded)
    assert int(reloaded.original_amount) == scenario.VICTIM_AMOUNT_RAW


async def test_the_golden_case_produces_a_report(
    session: AsyncSession, golden_run: uuid.UUID
) -> None:
    run = await session.get(AnalysisRun, golden_run)
    assert run is not None
    user = await session.scalar(select(User))
    assert user is not None

    generated = await generator.generate(
        session, golden_run, run.case_id, user.id, ReportFormat.PDF
    )

    from app.db.models.output import Report

    stored = await session.get(Report, generated.report_id)
    assert stored is not None
    assert generated.path.read_bytes().startswith(b"%PDF-")
    assert generator.verify(stored) is True


async def test_the_dust_branch_is_pruned_and_still_accounted(
    session: AsyncSession, golden_run: uuid.UUID
) -> None:
    """Below the taint threshold, so it is not followed — and it is not lost either."""
    actual = await observed(session, golden_run)

    pruned = actual["trace"]["pruned_branches"]
    assert [p["to"] for p in pruned] == ["DUST"]
    assert pruned[0]["reason"]
    # It never became a node, and its value is recorded against the address it left.
    assert "DUST" not in {n["address"] for n in actual["nodes"]}
    scam = next(n for n in actual["nodes"] if n["address"] == "SCAM")
    assert int(scam["pruned_amount_raw"]) > 0


def test_the_expected_file_is_committed() -> None:
    """A regression lock nobody committed is not a lock."""
    assert EXPECTED_PATH.exists(), "tests/golden/expected.json must be committed"
    expected = json.loads(EXPECTED_PATH.read_text())
    assert expected["trace"]["node_count"] > 1
    assert expected["attributions"], "the golden case must attribute something"


def test_the_scenario_timestamps_are_fixed() -> None:
    """A golden case with a moving clock is not a lock."""
    assert datetime(2026, 8, 14, 9, 0, tzinfo=UTC) == scenario.BASE
    assert scenario.flows()[0]["block_timestamp"] == int(scenario.BASE.timestamp() * 1000)
