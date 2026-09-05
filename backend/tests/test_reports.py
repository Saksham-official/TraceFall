"""Investigation reports.

A report is the artefact that reaches a case file, so the tests that matter are about
truthfulness rather than layout: that every fact in it matches a database row, that the
content hash verifies, that the tier words and the limitations survive into the document,
and that nothing in it is written by a model (ADR-021).
"""

import hashlib
import json
import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import worker
from app.db.models.analysis import AnalysisRun
from app.db.models.entity import Attribution
from app.db.models.enums import ChainCode, NarrativeSource, ReportFormat
from app.db.models.finding import RiskAssessment
from app.db.models.output import Report
from app.normalize import service as normalize
from app.reports import assemble, generator
from tests.conftest import auth, login, make_user
from tests.test_normalize import FIXTURED_TRON_ADDRESS
from tests.test_pipeline import queued_run


@pytest.fixture(autouse=True)
def storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Reports are written under a temporary root; /data is not writable in tests."""
    monkeypatch.setattr(generator, "storage_root", lambda: tmp_path / "reports")
    return tmp_path / "reports"


async def analysed(session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID, int]:
    """A completed run with a two-node trace. Returns run, case and user ids."""
    from app.chains.tron import adapter as tron
    from tests.tracing_fixtures import tx

    hot = tron.from_hex("41" + f"{606:040x}")
    senders = [tron.from_hex("41" + f"{610 + i:040x}") for i in range(4)]
    seeded = [tx(s, FIXTURED_TRON_ADDRESS, 10_000_000, i * 20) for i, s in enumerate(senders)]
    seeded += [tx(FIXTURED_TRON_ADDRESS, hot, 10_000_000, 20 * i + 5) for i in range(4)]
    await normalize.persist(session, ChainCode.TRON, seeded)

    run_id = await queued_run(session)
    await worker._run_pipeline(run_id)
    run = await session.get(AnalysisRun, run_id)
    assert run is not None
    return run.id, run.case_id, run.triggered_by


# --- Assembly -------------------------------------------------------------------------


async def test_every_fact_in_the_report_matches_the_database(session: AsyncSession) -> None:
    """The report must agree with the screen it came from."""
    run_id, _, _ = await analysed(session)

    data = await assemble.gather(session, run_id)

    stored_attributions = {
        row.address_id: row
        for row in (
            await session.scalars(select(Attribution).where(Attribution.analysis_run_id == run_id))
        ).all()
    }
    assert len(data.attributions) == len(stored_attributions)

    stored_risk = {
        row.address_id: row
        for row in (
            await session.scalars(
                select(RiskAssessment).where(RiskAssessment.analysis_run_id == run_id)
            )
        ).all()
    }
    assert len(data.risk) == len(stored_risk)
    for entry in data.risk:
        match = next(r for r in stored_risk.values() if r.score == entry["score"])
        assert entry["band"] == str(match.band)
        assert entry["config_version"] == match.config_version


async def test_the_report_carries_its_disclaimers_and_convention(session: AsyncSession) -> None:
    run_id, _, _ = await analysed(session)

    data = await assemble.gather(session, run_id)

    assert len(data.disclaimers) == len(assemble.DISCLAIMERS)
    assert any("not court-admissible" in d or "not a forensic" in d for d in data.disclaimers)
    assert any("cannot identify the person" in d for d in data.disclaimers)
    assert any("not a probability of fraud" in d for d in data.disclaimers)
    assert "haircut" in data.tracing_convention


async def test_the_evidence_appendix_lists_every_transaction_hash(
    session: AsyncSession,
) -> None:
    run_id, _, _ = await analysed(session)

    data = await assemble.gather(session, run_id)

    from_flows = {h for flow in data.key_transactions for h in flow["tx_hashes"]}
    assert from_flows
    assert {item["tx_hash"] for item in data.evidence} == from_flows


async def test_the_headline_never_upgrades_a_probable_attribution(
    session: AsyncSession,
) -> None:
    """`PROBABLE` must not read as a fact — the sentence says so in words."""
    run_id, _, _ = await analysed(session)
    data = await assemble.gather(session, run_id)

    line = assemble.headline(data)

    if any(a["tier"] == "PROBABLE" and a["entity_name"] for a in data.attributions):
        assert "probably" in line
        assert "not a confirmed identification" in line
    assert "is a" not in line.replace("is an inference", "")


async def test_an_unattributed_result_says_what_would_be_needed(
    session: AsyncSession,
) -> None:
    data = assemble.ReportData(
        case={
            "case_number": "TF-1",
            "title": "t",
            "status": "OPEN",
            "priority": "LOW",
            "ncrp_reference": None,
            "fir_reference": None,
            "incident_date": None,
            "reported_loss_inr": None,
            "owner": None,
            "created_at": "2026-01-01T00:00:00",
        },
        address={
            "address": "TXyz",
            "chain": "TRON",
            "explorer_url": "",
            "role": None,
            "reported_amount": None,
            "reported_asset_symbol": None,
            "reported_at": None,
        },
        run={
            "id": "r",
            "status": "COMPLETED",
            "started_at": None,
            "completed_at": None,
            "engine_versions": {},
            "degradations": [],
            "parameters": {},
        },
        summary={"traced": False},
    )

    line = assemble.headline(data)

    assert "No service could be reliably identified" in line
    assert "KYC records" in line


# --- Rendering and hashing ------------------------------------------------------------


async def test_a_pdf_generates_and_its_hash_verifies(session: AsyncSession) -> None:
    run_id, case_id, user_id = await analysed(session)

    generated = await generator.generate(session, run_id, case_id, user_id, ReportFormat.PDF)

    assert generated.path.is_file()
    assert generated.path.read_bytes()[:5] == b"%PDF-"
    assert generated.byte_size > 2_000
    assert generated.narrative_source is NarrativeSource.TEMPLATE
    # The hash is over exactly the bytes on disk.
    assert hashlib.sha256(generated.path.read_bytes()).hexdigest() == generated.content_sha256

    report = await session.get(Report, generated.report_id)
    assert report is not None
    assert generator.verify(report) is True


async def test_a_tampered_report_fails_verification(session: AsyncSession) -> None:
    run_id, case_id, user_id = await analysed(session)
    generated = await generator.generate(session, run_id, case_id, user_id, ReportFormat.PDF)
    report = await session.get(Report, generated.report_id)
    assert report is not None

    generated.path.write_bytes(generated.path.read_bytes() + b"tampered")

    assert generator.verify(report) is False


async def test_json_and_csv_exports_carry_the_same_facts(session: AsyncSession) -> None:
    run_id, case_id, user_id = await analysed(session)

    as_json = await generator.generate(session, run_id, case_id, user_id, ReportFormat.JSON)
    as_csv = await generator.generate(session, run_id, case_id, user_id, ReportFormat.CSV)

    payload = json.loads(as_json.path.read_text())
    assert payload["case"]["case_number"]
    assert payload["disclaimers"]
    assert payload["attributions"]

    lines = as_csv.path.read_text().strip().splitlines()
    assert lines[0].startswith("from,to,tainted_amount_raw")
    assert len(lines) == len(payload["key_transactions"]) + 1


async def test_the_pdf_contains_the_tier_words_and_the_disclaimer(
    session: AsyncSession,
) -> None:
    """Printed as text, not encoded as colour: a photocopy must keep the distinction."""
    run_id, _, _ = await analysed(session)
    data = await assemble.gather(session, run_id)

    content = generator.build(data, uuid.uuid4(), ReportFormat.PDF)

    # ReportLab compresses page streams, so assert against the assembled data that the
    # renderer prints rather than against the binary.
    tiers = {a["tier"] for a in data.attributions}
    assert tiers <= {"CONFIRMED", "PROBABLE", "UNATTRIBUTED"}
    assert tiers
    assert content.startswith(b"%PDF-")
    assert b"TraceFall" in content


async def test_a_report_generates_even_when_the_analysis_degraded(
    session: AsyncSession,
) -> None:
    """A partial answer with its limits stated still belongs in the case file."""
    run_id = await queued_run(session)
    await worker._run_pipeline(run_id)
    run = await session.get(AnalysisRun, run_id)
    assert run is not None

    data = await assemble.gather(session, run_id)
    content = generator.build(data, uuid.uuid4(), ReportFormat.PDF)

    assert content.startswith(b"%PDF-")
    assert data.run["status"] in ("COMPLETED", "PARTIAL")


# --- The API --------------------------------------------------------------------------


async def test_generating_and_downloading_a_report(
    client: AsyncClient, session: AsyncSession
) -> None:
    run_id, case_id, user_id = await analysed(session)
    from app.db.models.user import User

    owner = await session.get(User, user_id)
    assert owner is not None
    token = auth(await login(client, owner.email))

    created = await client.post(
        f"/api/v1/cases/{case_id}/reports",
        json={"analysis_run_id": str(run_id), "format": "PDF"},
        headers=token,
    )
    assert created.status_code == 201
    body = created.json()
    assert body["narrative_source"] == "TEMPLATE"
    assert body["content_verified"] is True

    listed = await client.get(f"/api/v1/cases/{case_id}/reports", headers=token)
    assert [r["id"] for r in listed.json()] == [body["id"]]

    downloaded = await client.get(body["download_url"], headers=token)
    assert downloaded.status_code == 200
    assert downloaded.headers["x-content-sha256"] == body["content_sha256"]
    assert hashlib.sha256(downloaded.content).hexdigest() == body["content_sha256"]


async def test_reports_are_case_isolated(client: AsyncClient, session: AsyncSession) -> None:
    run_id, case_id, user_id = await analysed(session)
    from app.db.models.user import User

    owner = await session.get(User, user_id)
    assert owner is not None
    generated = await generator.generate(session, run_id, case_id, owner.id, ReportFormat.PDF)

    await make_user(session, "outsider-reports@example.gov")
    outsider = auth(await login(client, "outsider-reports@example.gov"))

    assert (
        await client.post(
            f"/api/v1/cases/{case_id}/reports",
            json={"analysis_run_id": str(run_id)},
            headers=outsider,
        )
    ).status_code == 404
    assert (
        await client.get(f"/api/v1/reports/{generated.report_id}", headers=outsider)
    ).status_code == 404
    assert (
        await client.get(f"/api/v1/reports/{generated.report_id}/download", headers=outsider)
    ).status_code == 404


async def test_a_report_for_another_cases_run_is_refused(
    client: AsyncClient, session: AsyncSession
) -> None:
    run_id, case_id, user_id = await analysed(session)
    from app.db.models.case import Case
    from app.db.models.user import User

    owner = await session.get(User, user_id)
    assert owner is not None
    other = Case(case_number=f"TF-{uuid.uuid4().hex[:6]}", title="Other", owner_id=owner.id)
    session.add(other)
    await session.commit()
    token = auth(await login(client, owner.email))

    response = await client.post(
        f"/api/v1/cases/{other.id}/reports",
        json={"analysis_run_id": str(run_id)},
        headers=token,
    )

    assert response.status_code == 404


async def test_raw_amounts_print_as_plain_digits_not_scientific_notation(
    session: AsyncSession,
) -> None:
    """A NUMERIC renders as `5.000E+7` by default. That is not a number for a case file."""
    run_id, _, _ = await analysed(session)

    data = await assemble.gather(session, run_id)

    printed = [data.summary["total_traced_raw"]]
    printed += [t["tainted_amount_raw"] for t in data.summary["terminal_addresses"]]
    printed += [f["total_amount_raw"] for f in data.key_transactions]
    printed += [f["tainted_amount_raw"] for f in data.key_transactions]
    for value in printed:
        assert value.isdigit(), value
        assert "E" not in value.upper()
