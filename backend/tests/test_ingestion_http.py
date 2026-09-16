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
async def test_provider_credentials_are_redacted_from_response_metadata() -> None:
    respx.get(TRON_URL).mock(return_value=httpx.Response(200, json={"data": []}))
    response = await http.fetch("etherscan", TRON_URL, {"apikey": "SECRET", "limit": 5}, 100)
    assert response.params == {"apikey": "[REDACTED]", "limit": 5}
    assert "SECRET" not in repr(response)


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


# --- Provider-specific quirks ----------------------------------------------------

ETH_URL = "https://api.etherscan.io/api"
BLOCKSCOUT_URL = "https://eth.blockscout.com/api"


def _rows(n: int, timestamp: int = 1_700_000_000) -> list[dict]:
    return [{"hash": f"0x{i:064x}", "timeStamp": str(timestamp), "value": "1"} for i in range(n)]


def _ok(rows: list[dict]) -> httpx.Response:
    return httpx.Response(200, json={"status": "1", "message": "OK", "result": rows})


@respx.mock
async def test_blockscout_is_primary_and_needs_no_key() -> None:
    """Etherscan now rejects every keyless request, so Blockscout leads."""
    blockscout = respx.get(BLOCKSCOUT_URL).mock(return_value=_ok(_rows(3)))
    etherscan = respx.get(ETH_URL).mock(return_value=httpx.Response(200, json={}))
    result = await ethereum.fetch_native_transfers("0x" + "ab" * 20)
    assert blockscout.called
    assert not etherscan.called
    assert result.provider_used == "blockscout"
    assert result.record_count == 3


@respx.mock
async def test_etherscan_is_skipped_entirely_without_a_key() -> None:
    respx.get(BLOCKSCOUT_URL).mock(return_value=httpx.Response(503))
    etherscan = respx.get(ETH_URL).mock(return_value=httpx.Response(200, json={}))
    with pytest.raises(ProviderUnavailable):
        await ethereum.fetch_native_transfers("0x" + "ab" * 20)
    assert not etherscan.called, "a keyless Etherscan call can only fail"


@respx.mock
async def test_etherscan_is_used_as_failover_when_a_key_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(get_settings(), "etherscan_api_key", "test-key")
    respx.get(BLOCKSCOUT_URL).mock(return_value=httpx.Response(503))
    etherscan = respx.get(ETH_URL).mock(return_value=_ok(_rows(2)))
    result = await ethereum.fetch_native_transfers("0x" + "ab" * 20)
    assert etherscan.called
    assert result.provider_used == "etherscan"


@respx.mock
async def test_in_band_rate_limiting_at_http_200_is_detected() -> None:
    """The quirk that matters: transport-level retry never sees this, so the adapter must."""
    respx.get(BLOCKSCOUT_URL).mock(
        return_value=httpx.Response(
            200, json={"status": "0", "message": "NOTOK", "result": "Max rate limit reached"}
        )
    )
    with pytest.raises((ProviderUnavailable, ProviderRateLimited)):
        await ethereum.fetch_token_transfers("0x" + "ab" * 20)


@respx.mock
async def test_missing_api_key_is_reported_as_unavailable_not_parsed() -> None:
    respx.get(BLOCKSCOUT_URL).mock(
        return_value=httpx.Response(
            200, json={"status": "0", "message": "NOTOK", "result": "Missing/Invalid API Key"}
        )
    )
    with pytest.raises(ProviderUnavailable):
        await ethereum.fetch_native_transfers("0x" + "ab" * 20)


@respx.mock
async def test_partial_index_notice_marks_the_result_incomplete() -> None:
    """Blockscout returns usable rows alongside a warning that its index is behind.

    Treating that as complete is exactly the silent-incompleteness failure that internal
    transactions exist to prevent — and it looks like success, which is worse.
    """
    respx.get(BLOCKSCOUT_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "1",
                "message": "Some internal transactions have not yet been processed",
                "result": _rows(3),
            },
        )
    )
    result = await ethereum.fetch_internal_transfers("0x" + "ab" * 20)
    assert result.record_count == 3, "the rows we did get are still useful"
    assert result.complete is False
    assert result.truncation_reason is TruncationReason.PROVIDER_ERROR


@respx.mock
async def test_no_transactions_found_is_an_empty_result_not_an_error() -> None:
    respx.get(BLOCKSCOUT_URL).mock(
        return_value=httpx.Response(
            200, json={"status": "0", "message": "No transactions found", "result": []}
        )
    )
    result = await ethereum.fetch_token_transfers("0x" + "ab" * 20)
    assert result.record_count == 0
    assert result.complete is True


@respx.mock
async def test_unexpected_payload_raises_a_typed_parse_error() -> None:
    respx.get(BLOCKSCOUT_URL).mock(return_value=httpx.Response(200, json={"unexpected": "shape"}))
    with pytest.raises((ProviderUnavailable, ProviderParseError)):
        await ethereum.fetch_native_transfers("0x" + "ab" * 20)


@respx.mock
async def test_pagination_stops_on_a_short_page() -> None:
    size = get_settings().page_size
    respx.get(BLOCKSCOUT_URL).mock(side_effect=[_ok(_rows(size)), _ok(_rows(7))])
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
    respx.get(BLOCKSCOUT_URL).mock(return_value=_ok(_rows(settings.page_size)))
    result = await ethereum.fetch_native_transfers("0x" + "ab" * 20)
    assert result.complete is False
    assert result.truncation_reason is TruncationReason.TRANSFER_LIMIT
