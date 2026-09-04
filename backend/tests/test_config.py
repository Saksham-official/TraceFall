import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_secret_key_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    """The app must refuse to start rather than run on a missing or weak key."""
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_secret_key_must_be_long_enough() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, secret_key="short")  # type: ignore[call-arg]


def test_cors_origins_split_on_commas() -> None:
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        secret_key="x" * 32,
        cors_origins="http://a, http://b",
    )
    assert settings.cors_origin_list == ["http://a", "http://b"]
