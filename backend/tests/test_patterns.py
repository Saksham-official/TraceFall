"""Pattern detection.

Every detector gets a positive fixture **and a paired negative one**, because a detector
that fires on everything is worse than no detector: it teaches an investigator to ignore
findings. The framework tests matter as much as the detectors — that a finding cannot
reach a report without its false-positive note, and that one broken detector does not cost
the investigator the other five.
"""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chains.tron import adapter as tron
from app.db.models.analysis import AnalysisRun
from app.db.models.blockchain import Address
from app.db.models.case import Case
from app.db.models.enums import AnalysisStatus, ChainCode, PatternType, Severity
from app.db.models.finding import PatternFinding
from app.graph import builder
from app.patterns import detectors, persistence
from app.patterns.base import REGISTRY, Detector, Finding, StageResult, Subject, register, run_all
from app.tracing.engine import trace
from app.tracing.models import TraceParams
from tests.conftest import make_user
from tests.tracing_fixtures import ASSET, BASE_TIME, fetcher, tx

# Well-formed TRON addresses, generated so none can be mistaken for a real wallet.
ROOT = tron.from_hex("41" + f"{101:040x}")
EXIT = tron.from_hex("41" + f"{102:040x}")


async def pattern_scaffold(session: AsyncSession) -> tuple[uuid.UUID, str]:
    user = await make_user(session, f"patterns-{uuid.uuid4().hex[:6]}@example.gov")
    case = Case(case_number=f"TF-{uuid.uuid4().hex[:6]}", title="Patterns", owner_id=user.id)
    address = Address(chain_id=1, address=ROOT)
    session.add_all([case, address])
    await session.flush()
    run = AnalysisRun(
        case_id=case.id,
        root_address_id=address.id,
        status=AnalysisStatus.RUNNING,
        triggered_by=user.id,
    )
    session.add(run)
    await session.commit()
    return run.id, ROOT


PARAMS = TraceParams(asset_key=ASSET, max_depth=4, fanout_cap=60, address_budget=200)


async def subject_from(transfers: list, root: str = "A", amount: int | None = None) -> Subject:
    """Build the real trace graph, then hand the detectors the transfers behind it."""
    amount = amount or sum(t.amount_raw for t in transfers if t.to_address == root)
    result = await trace(root, amount, fetcher(transfers), PARAMS)
    graph = builder.build(result)
    by_address: dict[str, list] = {address: [] for address in graph.nodes}
    for transfer in transfers:
        for address in (transfer.from_address, transfer.to_address):
            if address in by_address:
                by_address[address].append(transfer)
    return Subject(graph=graph, transfers=by_address)


def types(findings: list[Finding]) -> set[PatternType]:
    return {finding.pattern_type for finding in findings}


# --- FAN_OUT --------------------------------------------------------------------------


async def test_fan_out_fires_on_dispersal() -> None:
    transfers = [tx("VICTIM", "A", 1_200_000, 0)] + [
        tx("A", f"OUT{i:02d}", 100_000, 10 + i) for i in range(12)
    ]
    subject = await subject_from(transfers)

    findings = detectors.fan_out.run(subject, detectors.fan_out.config)

    assert [f.subject_address for f in findings] == ["A"]
    assert findings[0].metrics["recipient_count"] == 12
    assert len(findings[0].trigger_tx_hashes) == 12
    assert "12 different addresses" in findings[0].explanation


async def test_fan_out_does_not_fire_on_a_few_payments() -> None:
    """The paired negative: three recipients is a wallet, not a dispersal."""
    transfers = [tx("VICTIM", "A", 300_000, 0)] + [
        tx("A", f"OUT{i}", 100_000, 10 + i) for i in range(3)
    ]

    assert detectors.fan_out.run(await subject_from(transfers), detectors.fan_out.config) == []


async def test_fan_out_does_not_fire_when_the_dispersal_is_spread_over_months() -> None:
    """Twelve recipients over a year is spending. The window is what makes it a pattern."""
    transfers = [tx("VICTIM", "A", 1_200_000, 0)] + [
        tx("A", f"OUT{i:02d}", 100_000, 10 + i * 43_200) for i in range(12)
    ]

    assert detectors.fan_out.run(await subject_from(transfers), detectors.fan_out.config) == []


# --- FAN_IN ---------------------------------------------------------------------------


async def test_fan_in_fires_on_consolidation() -> None:
    transfers = [tx(f"IN{i:02d}", "A", 100_000, i) for i in range(10)]
    transfers.append(tx("A", "EXIT", 1_000_000, 100))
    subject = await subject_from(transfers)

    findings = detectors.fan_in.run(subject, detectors.fan_in.config)

    assert [f.subject_address for f in findings] == ["A"]
    assert findings[0].metrics["sender_count"] == 10


async def test_fan_in_does_not_fire_on_a_handful_of_deposits() -> None:
    transfers = [tx(f"IN{i}", "A", 100_000, i) for i in range(3)]
    transfers.append(tx("A", "EXIT", 300_000, 100))

    assert detectors.fan_in.run(await subject_from(transfers), detectors.fan_in.config) == []


# --- RAPID_TRANSFER -------------------------------------------------------------------


async def test_rapid_transfer_fires_when_funds_pass_straight_through() -> None:
    transfers = [
        tx("VICTIM", "A", 500_000, 0),
        tx("A", "B", 500_000, 2),
        tx("VICTIM", "A", 500_000, 60),
        tx("A", "B", 500_000, 61),
    ]
    subject = await subject_from(transfers)

    findings = detectors.rapid_transfer.run(subject, detectors.rapid_transfer.config)

    assert [f.subject_address for f in findings] == ["A"]
    assert findings[0].metrics["occurrences"] == 2
    assert findings[0].metrics["fastest_seconds"] == 60


async def test_rapid_transfer_does_not_fire_when_funds_rest() -> None:
    """The paired negative: value held for days is a destination, not a relay."""
    transfers = [
        tx("VICTIM", "A", 500_000, 0),
        tx("A", "B", 500_000, 4_320),
        tx("VICTIM", "A", 500_000, 5_000),
        tx("A", "B", 500_000, 10_000),
    ]

    findings = detectors.rapid_transfer.run(
        await subject_from(transfers), detectors.rapid_transfer.config
    )
    assert findings == []


# --- PEEL_CHAIN -----------------------------------------------------------------------


async def test_peel_chain_fires_on_a_forwarding_chain() -> None:
    transfers = [tx("VICTIM", "A", 1_000_000, 0)]
    balance, cursor = 1_000_000, "A"
    for i in range(4):
        peel = balance // 20
        transfers.append(tx(cursor, f"PEEL{i}", peel, 10 + i))
        transfers.append(tx(cursor, f"HOP{i}", balance - peel, 10 + i))
        balance, cursor = balance - peel, f"HOP{i}"
    subject = await subject_from(transfers)

    findings = detectors.peel_chain.run(subject, detectors.peel_chain.config)

    assert findings
    assert findings[0].metrics["chain_length"] >= 3
    assert findings[0].trigger_tx_hashes


async def test_peel_chain_does_not_fire_on_an_even_split() -> None:
    """The paired negative: splitting value in half is not peeling."""
    transfers = [
        tx("VICTIM", "A", 1_000_000, 0),
        tx("A", "B", 500_000, 10),
        tx("A", "C", 500_000, 10),
        tx("B", "D", 250_000, 20),
        tx("B", "E", 250_000, 20),
    ]

    findings = detectors.peel_chain.run(await subject_from(transfers), detectors.peel_chain.config)
    assert findings == []


# --- DORMANCY_BURST -------------------------------------------------------------------


async def test_dormancy_burst_fires_after_a_long_quiet_period() -> None:
    transfers = [
        tx("VICTIM", "A", 1_000_000, 0),
        tx("A", "B", 300_000, 200 * 1_440),
        tx("A", "C", 300_000, 200 * 1_440 + 30),
        tx("A", "D", 300_000, 200 * 1_440 + 60),
    ]
    subject = await subject_from(transfers)

    findings = detectors.dormancy_burst.run(subject, detectors.dormancy_burst.config)

    assert [f.subject_address for f in findings] == ["A"]
    assert findings[0].metrics["dormant_days"] == 200
    assert findings[0].severity is Severity.MEDIUM


async def test_dormancy_burst_does_not_fire_on_steady_activity() -> None:
    transfers = [tx("VICTIM", "A", 1_000_000, 0)] + [
        tx("A", f"OUT{i}", 200_000, (i + 1) * 1_440) for i in range(4)
    ]

    findings = detectors.dormancy_burst.run(
        await subject_from(transfers), detectors.dormancy_burst.config
    )
    assert findings == []


# --- STRUCTURING ----------------------------------------------------------------------


async def test_structuring_fires_on_repeated_identical_amounts() -> None:
    transfers = [tx("VICTIM", "A", 900_000, 0)] + [
        tx("A", f"OUT{i}", 300_000, 10 + i) for i in range(3)
    ]
    subject = await subject_from(transfers)

    findings = detectors.structuring.run(subject, detectors.structuring.config)

    assert [f.subject_address for f in findings] == ["A"]
    assert findings[0].metrics["repeat_count"] == 3
    assert findings[0].metrics["amount_raw"] == "300000"


async def test_structuring_does_not_fire_on_varied_amounts() -> None:
    transfers = [tx("VICTIM", "A", 900_000, 0)] + [
        tx("A", f"OUT{i}", 100_000 * (i + 1), 10 + i) for i in range(3)
    ]

    findings = detectors.structuring.run(
        await subject_from(transfers), detectors.structuring.config
    )
    assert findings == []


# --- The framework --------------------------------------------------------------------


async def test_every_finding_carries_a_false_positive_note() -> None:
    """Asserted generically, so a new detector cannot ship without one (FR-66)."""
    transfers = [tx("VICTIM", "A", 1_200_000, 0)] + [
        tx("A", f"OUT{i:02d}", 100_000, 10 + i) for i in range(12)
    ]

    result = run_all(await subject_from(transfers))

    assert result.findings
    for finding in result.findings:
        assert finding.false_positive_note.strip(), finding
        assert finding.explanation.strip(), finding
        assert finding.detector_version


def test_a_detector_without_a_false_positive_note_cannot_be_registered() -> None:
    with pytest.raises(ValueError, match="false_positive_note"):

        @register(PatternType.FAN_OUT, config={}, false_positive_note="   ")
        def careless(subject: Subject, config: dict) -> list[Finding]:
            return []


async def test_a_broken_detector_degrades_itself_not_the_stage() -> None:
    """One bad detector must not cost an investigator every other finding."""

    def explode(subject: Subject, config: dict) -> list[Finding]:
        raise RuntimeError("detector is broken")

    broken = Detector(PatternType.FAN_OUT, {}, "note", explode)
    transfers = [tx(f"IN{i:02d}", "A", 100_000, i) for i in range(10)]
    transfers.append(tx("A", "EXIT", 1_000_000, 100))

    result = run_all(await subject_from(transfers), [broken, detectors.fan_in])

    assert result.degraded is True
    assert result.unavailable[0]["pattern_type"] == "FAN_OUT"
    assert "detector is broken" in result.unavailable[0]["reason"]
    assert types(result.findings) == {PatternType.FAN_IN}


async def test_every_finding_cites_the_transactions_that_triggered_it() -> None:
    """No finding may dead-end in 'trust us'."""
    transfers = [tx(f"IN{i:02d}", "A", 100_000, i) for i in range(10)]
    transfers += [tx("A", f"OUT{i:02d}", 90_000, 100 + i) for i in range(10)]

    result = run_all(await subject_from(transfers))

    assert result.findings
    for finding in result.findings:
        assert finding.trigger_tx_hashes, finding.pattern_type


def test_every_registered_detector_declares_its_thresholds() -> None:
    assert REGISTRY
    for detector in REGISTRY:
        assert detector.false_positive_note.strip()
        assert isinstance(detector.config, dict)


async def test_a_quiet_two_hop_trace_produces_no_findings() -> None:
    """The most important negative: the ordinary case must stay quiet."""
    transfers = [
        tx("VICTIM", "A", 500_000, 0),
        tx("A", "B", 500_000, 4_320),
        tx("B", "C", 500_000, 8_640),
    ]

    result = run_all(await subject_from(transfers))

    assert result.findings == []
    assert result.degraded is False


def test_the_window_helper_finds_the_densest_run() -> None:
    from app.patterns.detectors import _within_window

    spread = [tx("A", f"B{i}", 1, minutes=i * 60 * 24 * 3) for i in range(3)]
    clustered = [tx("A", f"C{i}", 1, minutes=100_000 + i) for i in range(5)]

    densest = _within_window(sorted(spread + clustered, key=lambda t: t.block_time), hours=24)

    assert len(densest) == 5
    assert all(t.block_time - BASE_TIME >= timedelta(minutes=100_000) for t in densest)


# --- Persistence ---------------------------------------------------------------------


async def test_findings_are_stored_with_their_note_and_triggers(session: AsyncSession) -> None:
    """`false_positive_note` is NOT NULL, so FR-66 is enforced twice — registry and schema."""
    run_id, root = await pattern_scaffold(session)
    transfers = [tx(f"IN{i:02d}", root, 100_000, i) for i in range(10)]
    transfers.append(tx(root, EXIT, 1_000_000, 100))
    result = run_all(await subject_from(transfers, root=root, amount=1_000_000))

    written = await persistence.save(session, run_id, ChainCode.TRON, result)

    assert written == len(result.findings) > 0
    rows = (await session.scalars(select(PatternFinding))).all()
    for row in rows:
        assert row.false_positive_note.strip()
        assert row.explanation.strip()
        assert row.trigger_tx_hashes
        assert row.involved_address_ids
        assert row.detector_version


async def test_a_run_with_no_findings_writes_nothing(session: AsyncSession) -> None:
    run_id, root = await pattern_scaffold(session)
    quiet = StageResult()

    assert await persistence.save(session, run_id, ChainCode.TRON, quiet) == 0
    assert (await session.scalars(select(PatternFinding))).all() == []
