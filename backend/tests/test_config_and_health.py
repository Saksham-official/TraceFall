import pytest
from httpx import AsyncClient
from pydantic import ValidationError

from app import __version__
from app.core.config import Settings
from app.core.logging import redact


def test_secret_key_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    """The app must refuse to start rather than run on a missing key."""
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_secret_key_must_be_long_enough() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, secret_key="short")  # type: ignore[call-arg]


def test_live_mode_defaults_to_true() -> None:
    """A fresh configuration uses real providers unless offline mode is explicit."""
    settings = Settings(_env_file=None, secret_key="x" * 32)  # type: ignore[call-arg]
    assert settings.live_mode is True


def test_cors_origins_split_on_commas() -> None:
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None, secret_key="x" * 32, cors_origins="http://a, http://b"
    )
    assert settings.cors_origin_list == ["http://a", "http://b"]


def test_alembic_url_drops_the_async_driver() -> None:
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        secret_key="x" * 32,
        database_url="postgresql+asyncpg://u:p@h:5432/d",
    )
    assert settings.sync_database_url == "postgresql://u:p@h:5432/d"


@pytest.mark.parametrize(
    "message",
    [
        "SECRET_KEY=hunter2abcdef",
        "ETHERSCAN_API_KEY: ABCD1234",
        "password='swordfish'",
        "refresh_token=eyJhbGciOi",
    ],
)
def test_secrets_are_redacted_from_logs(message: str) -> None:
    """A careless log.info(config) must not leak a credential."""
    redacted = redact(message)
    assert "***" in redacted
    for leaked in ("hunter2abcdef", "ABCD1234", "swordfish", "eyJhbGciOi"):
        assert leaked not in redacted


async def test_health_reports_version_and_mode(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == __version__
    assert body["providers"] == []  # populated in Phase 3
    assert body["queue_reachable"] is True


async def test_unhandled_errors_leak_nothing(client: AsyncClient) -> None:
    response = await client.get("/api/v1/cases/not-a-uuid", headers={"Authorization": "Bearer x"})
    assert response.status_code in (401, 422)
    assert "Traceback" not in response.text
