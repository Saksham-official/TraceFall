"""Transport behaviour: retries, backoff, failover, and the provider quirks that would
otherwise silently lose data."""

import httpx
import pytest
import respx

from app.chains import ethereum
from app.chains.base import (
    ProviderParseError,
    ProviderRateLimited,
    ProviderUnavailable,
    TruncationReason,
)
from app.core.config import get_settings
from app.ingestion import http

TRON_URL = "https://api.trongrid.io/v1/accounts/TX/transactions/trc20"


@pytest.fixture(autouse=True)
async def _transport_mode(monkeypatch: pytest.MonkeyPatch, clean_database: None) -> None:
    """These tests exercise the network path, so live mode is set explicitly rather than
    inherited from the environment. Backoff is asserted by call count, not by waiting."""
    monkeypatch.setattr(get_settings(), "live_mode", True)

    async def instant(_seconds: float) -> None:
        return None

    monkeypatch.setattr(http.asyncio, "sleep", instant)


@respx.mock
async def test_successful_request_returns_the_raw_body() -> None:
    route = respx.get(TRON_URL).mock(return_value=httpx.Response(200, json={"data": [1]}))
    response = await http.fetch("trongrid", TRON_URL, {"limit": 5}, 100)
    assert route.called
    assert response.status == 200
    assert response.json() == {"data": [1]}
    assert response.sha256


@respx.mock
async def test_rate_limit_is_retried_then_raises() -> None:
    route = respx.get(TRON_URL).mock(
        return_value=httpx.Response(429, headers={"Retry-After": "1"}, text="slow down")
    )
    with pytest.raises(ProviderRateLimited):
        await http.fetch("trongrid", TRON_URL, {}, 100)
    assert route.call_count == get_settings().http_max_retries + 1


@respx.mock
async def test_rate_limit_that_clears_succeeds() -> None:
    respx.get(TRON_URL).mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "1"}),
            httpx.Response(200, json={"data": []}),
        ]
    )
    response = await http.fetch("trongrid", TRON_URL, {}, 100)
    assert response.status == 200


@respx.mock
async def test_server_error_is_retried() -> None:
    respx.get(TRON_URL).mock(
        side_effect=[httpx.Response(503), httpx.Response(502), httpx.Response(200, json={})]
    )
    assert (await http.fetch("trongrid", TRON_URL, {}, 100)).status == 200


@respx.mock
async def test_timeout_is_retried_then_raises() -> None:
    route = respx.get(TRON_URL).mock(side_effect=httpx.ReadTimeout("timed out"))
    with pytest.raises(ProviderUnavailable):
        await http.fetch("trongrid", TRON_URL, {}, 100)
    assert route.call_count == get_settings().http_max_retries + 1


@respx.mock
async def test_client_error_is_not_retried() -> None:
    """A 4xx is the provider's considered answer, not a transient fault."""
    route = respx.get(TRON_URL).mock(return_value=httpx.Response(404))
    with pytest.raises(ProviderUnavailable):
        await http.fetch("trongrid", TRON_URL, {}, 100)
    assert route.call_count == 1


# --- Etherscan-specific quirks ---------------------------------------------------

ETH_URL = "https://api.etherscan.io/api"
BLOCKSCOUT_URL = "https://eth.blockscout.com/api"


def _rows(n: int, timestamp: int = 1_700_000_000) -> list[dict]:
    return [{"hash": f"0x{i:064x}", "timeStamp": str(timestamp), "value": "1"} for i in range(n)]


@respx.mock
async def test_etherscan_reports_rate_limiting_as_http_200() -> None:
    """The quirk that matters: transport-level retry never sees this, so the adapter must."""
    respx.get(ETH_URL).mock(
        return_value=httpx.Response(
            200, json={"status": "0", "message": "NOTOK", "result": "Max rate limit reached"}
        )
    )
    respx.get(BLOCKSCOUT_URL).mock(
        return_value=httpx.Response(
            200, json={"status": "0", "message": "NOTOK", "result": "Max rate limit reached"}
        )
    )
    with pytest.raises(ProviderUnavailable):
        await ethereum.fetch_token_transfers("0x" + "ab" * 20)


@respx.mock
async def test_no_transactions_found_is_an_empty_result_not_an_error() -> None:
    respx.get(ETH_URL).mock(
        return_value=httpx.Response(
            200, json={"status": "0", "message": "No transactions found", "result": []}
        )
    )
    result = await ethereum.fetch_token_transfers("0x" + "ab" * 20)
    assert result.record_count == 0
    assert result.complete is True


@respx.mock
async def test_ethereum_fails_over_to_blockscout() -> None:
    """Blockscout implements the Etherscan API shape, so one parser serves both."""
    respx.get(ETH_URL).mock(return_value=httpx.Response(503))
    blockscout = respx.get(BLOCKSCOUT_URL).mock(
        return_value=httpx.Response(200, json={"status": "1", "message": "OK", "result": _rows(3)})
    )
    result = await ethereum.fetch_native_transfers("0x" + "ab" * 20)
    assert blockscout.called
    assert result.provider_used == "blockscout"
    assert result.record_count == 3


@respx.mock
async def test_unexpected_payload_raises_a_typed_parse_error() -> None:
    respx.get(ETH_URL).mock(return_value=httpx.Response(200, json={"unexpected": "shape"}))
    respx.get(BLOCKSCOUT_URL).mock(return_value=httpx.Response(200, json={"unexpected": "shape"}))
    with pytest.raises((ProviderUnavailable, ProviderParseError)):
        await ethereum.fetch_native_transfers("0x" + "ab" * 20)


@respx.mock
async def test_pagination_stops_on_a_short_page() -> None:
    size = get_settings().page_size
    respx.get(ETH_URL).mock(
        side_effect=[
            httpx.Response(200, json={"status": "1", "message": "OK", "result": _rows(size)}),
            httpx.Response(200, json={"status": "1", "message": "OK", "result": _rows(7)}),
        ]
    )
    result = await ethereum.fetch_native_transfers("0x" + "ab" * 20)
    assert result.record_count == size + 7
    assert result.complete is True


@respx.mock
async def test_high_volume_address_is_truncated_and_flagged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Truncation is itself a finding: an address this active is probably a service."""
    settings = get_settings()
    monkeypatch.setattr(settings, "max_transfers_per_address", 300)
    respx.get(ETH_URL).mock(
        return_value=httpx.Response(
            200, json={"status": "1", "message": "OK", "result": _rows(settings.page_size)}
        )
    )
    result = await ethereum.fetch_native_transfers("0x" + "ab" * 20)
    assert result.complete is False
    assert result.truncation_reason is TruncationReason.TRANSFER_LIMIT
