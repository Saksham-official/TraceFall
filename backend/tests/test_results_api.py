"""The results endpoints: graph, attributions, patterns.

Two things are under test. That the pipeline's output is reachable and shaped as
API_SPEC.md section 6 describes — and that the integrity properties survive the trip to
JSON: the tier is never collapsed, `truncated` is always present, every pattern carries
its false-positive note, and a user who cannot see the case gets 404 rather than 403.
"""

import uuid

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import worker
from app.db.models.analysis import AnalysisRun, Trace
from app.db.models.enums import ChainCode
from app.normalize import service as normalize
from tests.conftest import auth, login, make_user
from tests.test_normalize import FIXTURED_TRON_ADDRESS
from tests.test_pipeline import queued_run


async def completed_run(session: AsyncSession) -> tuple[uuid.UUID, str, str]:
    """A finished run with a real two-node trace, plus the owner's token email."""
    from app.chains.tron import adapter as tron
    from tests.tracing_fixtures import tx

    next_hop = tron.from_hex("41" + f"{909:040x}")
    senders = [tron.from_hex("41" + f"{910 + i:040x}") for i in range(3)]
    seeded = [
        tx(sender, FIXTURED_TRON_ADDRESS, 1_000_000, i * 10) for i, sender in enumerate(senders)
    ]
    seeded += [tx(FIXTURED_TRON_ADDRESS, next_hop, 1_000_000, 30 + i * 10) for i in range(3)]
    await normalize.persist(session, ChainCode.TRON, seeded)

    run_id = await queued_run(session)
    await worker._run_pipeline(run_id)
    run = await session.get(AnalysisRun, run_id)
    assert run is not None
    owner = await session.get(type(await _any_user(session)), run.triggered_by)
    assert owner is not None
    return run_id, owner.email, next_hop


async def _any_user(session: AsyncSession):  # type: ignore[no-untyped-def]
    from app.db.models.user import User

    user = await session.scalar(select(User))
    assert user is not None
    return user


async def token_for(client: AsyncClient, email: str) -> str:
    return await login(client, email)


# --- Graph ---------------------------------------------------------------------------


async def test_the_graph_endpoint_returns_a_render_ready_payload(
    client: AsyncClient, session: AsyncSession
) -> None:
    run_id, email, next_hop = await completed_run(session)

    response = await client.get(
        f"/api/v1/analyses/{run_id}/graph", headers=auth(await token_for(client, email))
    )

    assert response.status_code == 200
    body = response.json()
    assert body["root"] == FIXTURED_TRON_ADDRESS
    assert {node["address"] for node in body["nodes"]} == {FIXTURED_TRON_ADDRESS, next_hop}
    assert body["edges"][0]["tx_hashes"], "every edge keeps its route back to raw evidence"
    # Raw amounts cross the wire as strings; a JSON number cannot hold them exactly.
    assert isinstance(body["nodes"][0]["tainted_amount_raw"], str)


async def test_truncated_is_always_present(client: AsyncClient, session: AsyncSession) -> None:
    """Silently hiding half a fund flow is the thing this flag exists to prevent."""
    run_id, email, _ = await completed_run(session)
    token = await token_for(client, email)

    full = await client.get(f"/api/v1/analyses/{run_id}/graph", headers=auth(token))
    capped = await client.get(f"/api/v1/analyses/{run_id}/graph?max_nodes=1", headers=auth(token))

    for body in (full.json(), capped.json()):
        # The flag and the count must agree. A truncated payload that dropped nothing
        # would train investigators to ignore the one flag they must not ignore.
        assert body["truncated"] == (body["omitted_node_count"] > 0)
    assert full.json()["truncated"] is False
    assert capped.json()["total_nodes"] == full.json()["total_nodes"]


async def test_the_graph_reports_what_the_trace_could_not_reach(
    client: AsyncClient, session: AsyncSession
) -> None:
    """The gaps travel with the picture, not in a call the investigator must know to make."""
    run_id, email, next_hop = await completed_run(session)

    body = (
        await client.get(
            f"/api/v1/analyses/{run_id}/graph", headers=auth(await token_for(client, email))
        )
    ).json()

    assert [u["address"] for u in body["unavailable_addresses"]] == [next_hop]
    assert "pruned_branches" in body


async def test_the_graph_carries_its_derived_measures(
    client: AsyncClient, session: AsyncSession
) -> None:
    run_id, email, _ = await completed_run(session)

    measures = (
        await client.get(
            f"/api/v1/analyses/{run_id}/graph", headers=auth(await token_for(client, email))
        )
    ).json()["measures"]

    assert measures["components"] == 1
    assert measures["cycles"] == []
    assert "chokepoints" in measures
    assert measures["highest_value_path"]


async def test_a_run_with_no_trace_is_a_404(client: AsyncClient, session: AsyncSession) -> None:
    run_id = await queued_run(session)
    run = await session.get(AnalysisRun, run_id)
    assert run is not None
    user = await _any_user(session)

    response = await client.get(
        f"/api/v1/analyses/{run_id}/graph", headers=auth(await token_for(client, user.email))
    )

    assert response.status_code == 404
    assert await session.scalar(select(Trace).where(Trace.analysis_run_id == run_id)) is None


# --- Attributions --------------------------------------------------------------------


async def test_attributions_keep_their_tier_and_evidence(
    client: AsyncClient, session: AsyncSession
) -> None:
    run_id, email, _ = await completed_run(session)

    body = (
        await client.get(
            f"/api/v1/analyses/{run_id}/attributions",
            headers=auth(await token_for(client, email)),
        )
    ).json()

    assert body
    for row in body:
        assert row["tier"] in ("CONFIRMED", "PROBABLE", "UNATTRIBUTED")
        assert row["evidence"]
        assert row["engine_version"]
        # The tiers are never collapsed: a confirmed claim carries no probability, and an
        # unattributed one names no entity.
        if row["tier"] == "CONFIRMED":
            assert row["confidence"] is None
        if row["tier"] == "UNATTRIBUTED":
            assert row["entity_name"] is None


async def test_attributions_filter_by_tier(client: AsyncClient, session: AsyncSession) -> None:
    run_id, email, _ = await completed_run(session)
    token = await token_for(client, email)

    filtered = await client.get(
        f"/api/v1/analyses/{run_id}/attributions?tier=UNATTRIBUTED", headers=auth(token)
    )

    assert filtered.status_code == 200
    assert all(row["tier"] == "UNATTRIBUTED" for row in filtered.json())


# --- Patterns ------------------------------------------------------------------------


async def test_every_pattern_returned_carries_its_false_positive_note(
    client: AsyncClient, session: AsyncSession
) -> None:
    """A pattern shown without what else produces its shape will be read as a conclusion."""
    run_id, email, _ = await completed_run(session)

    response = await client.get(
        f"/api/v1/analyses/{run_id}/patterns", headers=auth(await token_for(client, email))
    )

    assert response.status_code == 200
    for finding in response.json():
        assert finding["false_positive_note"].strip()
        assert finding["explanation"].strip()
        assert finding["trigger_tx_hashes"]


# --- Isolation -----------------------------------------------------------------------


async def test_another_investigator_gets_404_not_403(
    client: AsyncClient, session: AsyncSession
) -> None:
    """404, never 403 — the endpoint must not confirm the run exists (ADR-013)."""
    run_id, _, _ = await completed_run(session)
    await make_user(session, "outsider-results@example.gov")
    outsider = auth(await login(client, "outsider-results@example.gov"))

    for path in ("graph", "attributions", "patterns"):
        response = await client.get(f"/api/v1/analyses/{run_id}/{path}", headers=outsider)
        assert response.status_code == 404, path


async def test_an_unknown_run_is_also_404(client: AsyncClient, session: AsyncSession) -> None:
    await make_user(session, "known-results@example.gov")
    token = auth(await login(client, "known-results@example.gov"))

    response = await client.get(f"/api/v1/analyses/{uuid.uuid4()}/graph", headers=token)

    assert response.status_code == 404


async def test_the_endpoints_require_authentication(client: AsyncClient) -> None:
    for path in ("graph", "attributions", "patterns"):
        response = await client.get(f"/api/v1/analyses/{uuid.uuid4()}/{path}")
        assert response.status_code == 401, path


async def test_the_risk_endpoint_returns_the_breakdown(
    client: AsyncClient, session: AsyncSession
) -> None:
    run_id, email, _ = await completed_run(session)

    body = (
        await client.get(
            f"/api/v1/analyses/{run_id}/risk", headers=auth(await token_for(client, email))
        )
    ).json()

    assert body["nodes"]
    assert body["root"] is not None
    assert "Not a probability of fraud" in body["disclaimer"]
    for node in body["nodes"]:
        assert 0 <= node["score"] <= 100
        assert node["band"] in ("LOW", "MEDIUM", "HIGH", "CRITICAL")
        assert node["signals"], "the breakdown is never optional"
        assert node["config_version"]
        # Confidence rides alongside the score, never inside it.
        assert 0 < node["confidence"] <= 1


async def test_not_evaluated_stays_separate_from_zero_scoring(
    client: AsyncClient, session: AsyncSession
) -> None:
    """A missing signal must be visible, not indistinguishable from one that scored 0."""
    run_id, email, _ = await completed_run(session)

    body = (
        await client.get(
            f"/api/v1/analyses/{run_id}/risk", headers=auth(await token_for(client, email))
        )
    ).json()

    root = body["root"]
    assert root["not_evaluated"], "backward tracing and darknet labels are absent by design"
    for skipped in root["not_evaluated"]:
        assert skipped["reason"].strip()
    assert not ({n["name"] for n in root["not_evaluated"]} & {s["name"] for s in root["signals"]})


async def test_the_risk_endpoint_is_case_isolated(
    client: AsyncClient, session: AsyncSession
) -> None:
    run_id, _, _ = await completed_run(session)
    await make_user(session, "outsider-risk@example.gov")
    outsider = auth(await login(client, "outsider-risk@example.gov"))

    assert (
        await client.get(f"/api/v1/analyses/{run_id}/risk", headers=outsider)
    ).status_code == 404
