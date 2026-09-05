"""Cache, fixture routing, and request coalescing."""

from datetime import UTC, datetime

import pytest

from app.chains.base import RawResponse
from app.core.config import get_settings
from app.ingestion import cache, fixtures


def _response(body: bytes = b'{"data": []}') -> RawResponse:
    return RawResponse(
        provider="trongrid",
        endpoint="https://api.trongrid.io/v1/accounts/TX/transactions/trc20",
        params={"limit": 200},
        status=200,
        body=body,
        retrieved_at=datetime.now(UTC),
    )


def test_cache_key_is_stable_across_parameter_ordering() -> None:
    a = cache.cache_key("p", "/u", {"b": 2, "a": 1})
    b = cache.cache_key("p", "/u", {"a": 1, "b": 2})
    assert a == b


def test_cache_key_changes_with_parameters() -> None:
    assert cache.cache_key("p", "/u", {"page": 1}) != cache.cache_key("p", "/u", {"page": 2})


def test_fixture_key_excludes_time_derived_parameters() -> None:
    """A window computed as "last 90 days" differs every run; a fixture keyed on it could
    never be replayed."""
    base = {"limit": 200, "order_by": "block_timestamp,desc"}
    monday = fixtures.fixture_key(
        "trongrid", "/u", {**base, "min_timestamp": 1, "max_timestamp": 2}
    )
    tuesday = fixtures.fixture_key(
        "trongrid", "/u", {**base, "min_timestamp": 999, "max_timestamp": 1000}
    )
    assert monday == tuesday


def test_fixture_key_excludes_credentials() -> None:
    with_key = fixtures.fixture_key("etherscan", "/api", {"module": "account", "apikey": "SECRET"})
    without = fixtures.fixture_key("etherscan", "/api", {"module": "account"})
    assert with_key == without
    assert "SECRET" not in with_key


def test_fixture_key_still_distinguishes_real_differences() -> None:
    a = fixtures.fixture_key("etherscan", "/api", {"action": "txlist", "page": 1})
    b = fixtures.fixture_key("etherscan", "/api", {"action": "txlist", "page": 2})
    c = fixtures.fixture_key("etherscan", "/api", {"action": "tokentx", "page": 1})
    assert len({a, b, c}) == 3


async def test_cache_round_trip(clean_database: None) -> None:
    original = _response(b'{"data": [1, 2, 3]}')
    key = cache.cache_key("trongrid", original.endpoint, original.params)
    await cache.put(key, original)
    restored = await cache.get(key)
    assert restored is not None
    assert restored.body == original.body
    assert restored.sha256 == original.sha256
    assert restored.from_cache is True


async def test_cache_miss_returns_none(clean_database: None) -> None:
    assert await cache.get("trongrid:nothing-here") is None


def test_missing_fixture_names_the_capture_command() -> None:
    """Silently returning empty would look like an address with no activity."""
    with pytest.raises(fixtures.FixtureMissing) as exc:
        fixtures.load("trongrid", "trongrid:0123456789abcdef0123456789abcdef")
    message = str(exc.value)
    assert "capture_fixtures.py" in message
    assert "0123456789abcdef" in message


def test_fixture_root_is_anchored_to_the_backend_package() -> None:
    """Not to the working directory: the capture script and the tests must agree."""
    assert fixtures.fixture_root().is_absolute()
    assert fixtures.fixture_root().name == "chain_data"


def test_committed_fixtures_exist_and_are_real_provider_responses() -> None:
    captured = list(fixtures.fixture_root().rglob("*.json.gz"))
    assert captured, "no fixtures committed — the offline demo path would not work"
    response = fixtures.load("trongrid", f"trongrid:{captured[0].name.removesuffix('.json.gz')}")
    assert response.is_fixture is True
    assert response.status == 200
    assert isinstance(response.json(), dict)


def test_live_mode_defaults_to_fixtures() -> None:
    """A fresh clone runs offline with no API keys (ADR-009)."""
    assert get_settings().live_mode is False
