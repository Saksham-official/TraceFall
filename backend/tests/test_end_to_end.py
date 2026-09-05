"""The end-to-end investigation scenarios in TESTING_STRATEGY.md section 12.

The golden case lives in `test_golden_case.py` and locks exact numbers. These five cover
the *shapes* an investigator actually meets, and what each must be framed as. The framing
is the assertion: "the funds have not moved" and "we could not look" are different
findings, and a scenario that produces the wrong one is a product failure even when every
number in it is right.
"""

import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import worker
from app.core.config import get_settings
from app.db.models.analysis import AnalysisRun, Trace, TraceNode
from app.db.models.blockchain import Address, Chain
from app.db.models.case import Case, CaseAddress
from app.db.models.entity import Attribution
from app.db.models.enums import (
    AddressRole,
    AlertType,
    AnalysisStatus,
    AttributionTier,
    ChainCode,
    EntityType,
    ReportFormat,
    TerminationReason,
)
from app.db.models.finding import Alert, RiskAssessment
from app.labels import loader
from app.reports import assemble, generator
from tests import golden_scenario as scenario
from tests.conftest import make_user


def dataset(labels: list[dict[str, str]], name: str) -> loader.LabelFile:
    return loader.LabelFile.model_validate(
        {
            "source": {
                "name": name,
                "url": "https://example.test",
                "licence": "CC0",
                "reliability": "HIGH",
                "dataset_date": "2026-07-01",
            },
            "labels": labels,
        }
    )


async def run_scenario(
    session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    flows: list[dict[str, Any]],
    root: str,
    *,
    labels: list[dict[str, str]] | None = None,
    reported_amount: Decimal | None = None,
    case_number: str | None = None,
    fixture_addresses: list[str] | None = None,
    params: dict[str, Any] | None = None,
) -> uuid.UUID:
    """Write fixtures for one flow set, then run the whole pipeline over it."""
    monkeypatch.setattr(get_settings(), "fixture_path", str(tmp_path / "fixtures"))
    monkeypatch.setattr(get_settings(), "report_storage_path", str(tmp_path / "reports"))
    monkeypatch.setattr(get_settings(), "evidence_storage_path", str(tmp_path / "evidence"))
    _write(tmp_path / "fixtures", flows, fixture_addresses or _addresses(flows))

    if labels:
        await loader.ingest(session, dataset(labels, f"Scenario dataset {uuid.uuid4().hex[:6]}"))

    user = await make_user(session, f"e2e-{uuid.uuid4().hex[:6]}@example.gov")
    chain = await session.scalar(select(Chain).where(Chain.code == ChainCode.TRON))
    assert chain is not None
    address = await session.scalar(
        select(Address).where(Address.chain_id == chain.id, Address.address == root)
    )
    if address is None:
        address = Address(chain_id=chain.id, address=root)
        session.add(address)
    case = Case(
        case_number=case_number or f"TF-E2E-{uuid.uuid4().hex[:6]}",
        title="Scenario",
        owner_id=user.id,
    )
    session.add(case)
    await session.flush()
    session.add(
        CaseAddress(
            case_id=case.id,
            address_id=address.id,
            role=AddressRole.SUSPECT,
            added_by=user.id,
            reported_amount=reported_amount,
            reported_at=scenario.BASE if reported_amount else None,
        )
    )
    run = AnalysisRun(
        case_id=case.id,
        root_address_id=address.id,
        status=AnalysisStatus.QUEUED,
        triggered_by=user.id,
        params={"max_depth": 3, "time_window_days": 3650, **(params or {})},
    )
    session.add(run)
    await session.commit()

    await worker._run_pipeline(run.id)
    return run.id


def _addresses(flows: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    for row in flows:
        seen.update({row["from"], row["to"]})
    return sorted(seen)


def _write(root: Path, flows: list[dict[str, Any]], addresses: list[str]) -> None:
    import gzip
    import json

    from app.ingestion.fixtures import fixture_key

    for subject in addresses:
        mine = [r for r in flows if subject in (r["from"], r["to"])]
        for endpoint, body in (
            (f"https://api.trongrid.io/v1/accounts/{subject}/transactions", {"data": []}),
            (f"https://api.trongrid.io/v1/accounts/{subject}/transactions/trc20", {"data": mine}),
        ):
            params = {"limit": 200, "order_by": "block_timestamp,desc"}
            key = fixture_key("trongrid", endpoint, params)
            path = root / "trongrid" / f"{key.split(':', 1)[1]}.json.gz"
            path.parent.mkdir(parents=True, exist_ok=True)
            # Fixtures are stored gzipped; see app/ingestion/fixtures.py.
            path.write_bytes(
                gzip.compress(
                    json.dumps(
                        {
                            "provider": "trongrid",
                            "endpoint": endpoint,
                            "params": params,
                            "status": 200,
                            "captured_at": scenario.BASE.isoformat(),
                            "body": body,
                        }
                    ).encode()
                )
            )


async def _run(session: AsyncSession, run_id: uuid.UUID) -> AnalysisRun:
    run = await session.get(AnalysisRun, run_id)
    assert run is not None
    await session.refresh(run)
    return run


# --- Mixer case -----------------------------------------------------------------------


async def test_a_trace_reaching_a_mixer_stops_there_and_raises_an_alert(
    session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Downstream of a mixer is not the suspect's money any more, and the trail ends."""
    scam, mixer = scenario.address(0xA1), scenario.address(0xA2)
    flows = [
        scenario._transfer("v", 0, scenario.VICTIM, scam, 40_000_000_000, 0),
        scenario._transfer("m", 0, scam, mixer, 40_000_000_000, 30),
    ]

    run_id = await run_scenario(
        session,
        tmp_path,
        monkeypatch,
        flows,
        scam,
        labels=[
            {
                "chain": "TRON",
                "address": mixer,
                "entity": "Tornado Cash",
                "entity_type": "MIXER",
                "label_text": "Tornado Cash router",
            }
        ],
    )

    trace = await session.scalar(select(Trace).where(Trace.analysis_run_id == run_id))
    assert trace is not None
    reasons = {
        n.termination_reason
        for n in (
            await session.scalars(select(TraceNode).where(TraceNode.trace_id == trace.id))
        ).all()
    }
    assert TerminationReason.SERVICE_BOUNDARY in reasons

    attributions = await session.execute(
        select(Attribution).where(Attribution.analysis_run_id == run_id)
    )
    assert EntityType.MIXER in {row.entity_type for row in attributions.scalars()}

    alerts = (await session.scalars(select(Alert).where(Alert.analysis_run_id == run_id))).all()
    assert AlertType.MIXER_CONTACT in {a.alert_type for a in alerts}


# --- No-movement case -----------------------------------------------------------------


async def test_funds_that_have_not_moved_are_framed_as_good_news(
    session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A single-node trace is a finding an investigator acts on, not an empty result."""
    scam = scenario.address(0xB1)
    flows = [scenario._transfer("v", 0, scenario.VICTIM, scam, 40_000_000_000, 0)]

    run_id = await run_scenario(session, tmp_path, monkeypatch, flows, scam)

    trace = await session.scalar(select(Trace).where(Trace.analysis_run_id == run_id))
    assert trace is not None
    assert trace.node_count == 1
    node = await session.scalar(select(TraceNode).where(TraceNode.trace_id == trace.id))
    assert node is not None
    # NO_OUTFLOW, never DATA_UNAVAILABLE: we looked, and nothing had left.
    assert node.termination_reason is TerminationReason.NO_OUTFLOW

    run = await _run(session, run_id)
    assert run.status is AnalysisStatus.COMPLETED
    assert run.degradations == []


# --- Unattributable case --------------------------------------------------------------


async def test_an_unattributable_case_still_produces_a_useful_report(
    session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The case that earns the other two their credibility."""
    scam, onward = scenario.address(0xC1), scenario.address(0xC2)
    flows = [
        scenario._transfer("v", 0, scenario.VICTIM, scam, 40_000_000_000, 0),
        scenario._transfer("o", 0, scam, onward, 40_000_000_000, 30),
    ]

    run_id = await run_scenario(session, tmp_path, monkeypatch, flows, scam)

    tiers = {
        row.tier
        for row in (
            await session.scalars(select(Attribution).where(Attribution.analysis_run_id == run_id))
        ).all()
    }
    assert tiers == {AttributionTier.UNATTRIBUTED}

    report = await assemble.gather(session, run_id)
    headline = assemble.headline(report)
    assert "No service could be reliably identified" in headline
    assert "KYC records held by a VASP" in headline

    run = await _run(session, run_id)
    user_id = run.triggered_by
    generated = await generator.generate(session, run_id, run.case_id, user_id, ReportFormat.PDF)
    # A report with no attribution is still a report: the trace, the hashes, the limits.
    assert generated.path.read_bytes().startswith(b"%PDF-")
    assert report.evidence
    assert report.disclaimers


# --- Cross-case correlation -----------------------------------------------------------


async def test_a_second_case_on_the_same_address_is_correlated(
    session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two victims, one scam wallet — the signal an investigator most wants."""
    scam, onward = scenario.address(0xD1), scenario.address(0xD2)
    flows = [
        scenario._transfer("v", 0, scenario.VICTIM, scam, 40_000_000_000, 0),
        scenario._transfer("o", 0, scam, onward, 40_000_000_000, 30),
    ]

    await run_scenario(session, tmp_path, monkeypatch, flows, scam, case_number="TF-XCASE-1")
    second = await run_scenario(
        session, tmp_path, monkeypatch, flows, scam, case_number="TF-XCASE-2"
    )

    rows = await session.execute(
        select(RiskAssessment, Address.address)
        .join(Address, Address.id == RiskAssessment.address_id)
        .where(RiskAssessment.analysis_run_id == second)
    )
    root_row = next(row for row, address in rows if address == scam)
    fired = {s["name"]: s for s in root_row.signals}
    assert fired["cross_case_match"]["raw_value"] is True
    assert fired["cross_case_match"]["points"] > 0


# --- Degraded case --------------------------------------------------------------------


async def test_a_branch_with_no_fixture_degrades_the_run_without_losing_it(
    session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Partial data, stated. The run stays usable and says exactly what is missing."""
    scam, unreachable = scenario.address(0xE1), scenario.address(0xE2)
    flows = [
        scenario._transfer("v", 0, scenario.VICTIM, scam, 40_000_000_000, 0),
        scenario._transfer("o", 0, scam, unreachable, 40_000_000_000, 30),
    ]

    run_id = await run_scenario(
        session,
        tmp_path,
        monkeypatch,
        flows,
        scam,
        # The onward address is deliberately given no fixture.
        fixture_addresses=[scenario.VICTIM, scam],
    )

    run = await _run(session, run_id)
    assert run.status is AnalysisStatus.PARTIAL
    assert any(d["stage"] == "TRACING" for d in run.degradations)

    trace = await session.scalar(select(Trace).where(Trace.analysis_run_id == run_id))
    assert trace is not None
    assert [u["address"] for u in trace.unavailable] == [unreachable]
    reasons = {
        n.termination_reason
        for n in (
            await session.scalars(select(TraceNode).where(TraceNode.trace_id == trace.id))
        ).all()
    }
    # The distinction that matters: we could not look, so we do not claim nothing left.
    assert TerminationReason.DATA_UNAVAILABLE in reasons
    assert TerminationReason.NO_OUTFLOW not in reasons

    # And the partial answer is still worth having.
    report = await assemble.gather(session, run_id)
    assert report.summary["unavailable_addresses"] == [unreachable]
    assert generator.build(report, uuid.uuid4(), ReportFormat.PDF).startswith(b"%PDF-")
