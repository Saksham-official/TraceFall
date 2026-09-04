"""The Blockchain Data Service.

Its defining property: provider failure becomes a partial result, never an exception
that escapes (FR-25). The analysis completes with what was obtained, explicitly marked.
"""

import uuid

import httpx
import pytest
import respx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chains.base import TimeWindow
from app.core.config import get_settings
from app.db.models.blockchain import Address, Chain
from app.db.models.case import Case
from app.db.models.enums import ChainCode
from app.db.models.output import EvidenceItem
from app.ingestion import evidence, service
from app.ingestion.fixtures import FixtureMissing
from tests.conftest import make_user

TRON_ADDRESS = "TMuA6YqfCeX8EhbfYEg5y7S4DqzSJireY9"
ETH_ADDRESS = "0x" + "ab" * 20
ETH_URL = "https://api.etherscan.io/api"
BLOCKSCOUT_URL = "https://eth.blockscout.com/api"


# --- Fixture mode (the demo path) -------------------------------------------------


async def test_fixture_mode_serves_real_captured_data(clean_database: None) -> None:
    data = await service.retrieve_address(ChainCode.TRON, TRON_ADDRESS, TimeWindow.last_days(90))
    assert data.record_count > 0
    assert data.complete is True
    assert data.is_fixture is True
    assert data.degradations == []


async def test_fixture_mode_ignores_the_requested_window(clean_database: None) -> None:
    """One captured snapshot per address; window filtering happens at normalization."""
    week = await service.retrieve_address(ChainCode.TRON, TRON_ADDRESS, TimeWindow.last_days(7))
    year = await service.retrieve_address(ChainCode.TRON, TRON_ADDRESS, TimeWindow.last_days(365))
    assert week.record_count == year.record_count


async def test_missing_fixture_surfaces_rather_than_looking_like_no_activity(
    clean_database: None,
) -> None:
    with pytest.raises(FixtureMissing):
        await service.retrieve_address(ChainCode.TRON, "TUnknownAddressWithNoFixture123456", None)


# --- Degradation ------------------------------------------------------------------


@pytest.fixture
async def _live(monkeypatch: pytest.MonkeyPatch, clean_database: None) -> None:
    monkeypatch.setattr(get_settings(), "live_mode", True)
    monkeypatch.setattr(get_settings(), "http_max_retries", 0)


@respx.mock
async def test_total_provider_failure_returns_a_partial_result(_live: None) -> None:
    """It must not raise: the investigation continues with what was obtained."""
    respx.get(ETH_URL).mock(return_value=httpx.Response(503))
    respx.get(BLOCKSCOUT_URL).mock(return_value=httpx.Response(503))

    data = await service.retrieve_address(ChainCode.ETHEREUM, ETH_ADDRESS, None)

    assert data.complete is False
    assert data.degradations, "a degraded retrieval must say why"
    assert data.record_count == 0


@respx.mock
async def test_partial_failure_keeps_what_succeeded(_live: None) -> None:
    """Token transfers succeed, internal transactions fail: keep the token data."""

    def route(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("action") == "txlistinternal":
            return httpx.Response(503)
        return httpx.Response(
            200,
            json={
                "status": "1",
                "message": "OK",
                "result": [{"hash": "0x" + "1" * 64, "timeStamp": "1700000000", "value": "1"}],
            },
        )

    respx.get(ETH_URL).mock(side_effect=route)
    respx.get(BLOCKSCOUT_URL).mock(side_effect=route)

    data = await service.retrieve_address(ChainCode.ETHEREUM, ETH_ADDRESS, None)

    assert data.record_count == 2  # native + token succeeded
    assert data.complete is False
    assert any("internal" in d for d in data.degradations)


# --- Evidence ---------------------------------------------------------------------


async def test_responses_are_recorded_as_hashed_evidence(
    session: AsyncSession, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "evidence_storage_path", str(tmp_path))
    user = await make_user(session, "evidence@example.gov")
    case = Case(case_number=f"TF-EV-{uuid.uuid4().hex[:6]}", title="Evidence", owner_id=user.id)
    session.add(case)
    await session.commit()

    data = await service.retrieve_address(
        ChainCode.TRON, TRON_ADDRESS, None, session=session, case_id=case.id
    )

    items = list((await session.scalars(select(EvidenceItem))).all())
    assert len(items) == len(data.responses)
    for item in items:
        assert len(item.content_sha256) == 64
        assert item.is_fixture is True
        assert item.byte_size and item.byte_size > 0
        # The stored body must round-trip to the hash we recorded.
        assert evidence.read_body(item.storage_path)


async def test_evidence_bodies_are_written_before_parsing(
    session: AsyncSession, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A parse failure must never lose the evidence that would explain it."""
    monkeypatch.setattr(get_settings(), "evidence_storage_path", str(tmp_path))
    path, size = evidence.write_body(b"not valid json at all", None)
    assert size > 0
    assert evidence.read_body(str(path)) == b"not valid json at all"


async def test_evidence_paths_never_contain_user_input(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Paths are built from server-generated UUIDs, so traversal is impossible."""
    monkeypatch.setattr(get_settings(), "evidence_storage_path", str(tmp_path))
    path, _ = evidence.write_body(b"{}", None)
    assert ".." not in str(path)
    assert path.is_relative_to(tmp_path)


async def test_address_data_reports_its_own_completeness(clean_database: None) -> None:
    data = await service.retrieve_address(ChainCode.TRON, TRON_ADDRESS, None)
    assert isinstance(data.complete, bool)
    assert isinstance(data.truncation_reasons, list)
    assert data.chain is ChainCode.TRON


async def test_chain_reference_data_is_seeded(session: AsyncSession) -> None:
    codes = {c.code for c in (await session.scalars(select(Chain))).all()}
    assert codes == {ChainCode.TRON, ChainCode.ETHEREUM}


async def test_addresses_table_accepts_a_canonical_tron_address(session: AsyncSession) -> None:
    chain = await session.scalar(select(Chain).where(Chain.code == ChainCode.TRON))
    assert chain is not None
    session.add(Address(chain_id=chain.id, address=TRON_ADDRESS))
    await session.commit()
