"""Application settings, loaded from the environment.

Only the settings Phase 1 actually uses are declared. Unknown variables in .env are
ignored, so .env.example can stay ahead of the code as later phases land.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Literal["development", "production"] = "development"

    # No default: the app must refuse to start rather than run on a known key.
    secret_key: str = Field(min_length=32)

    # false serves everything from the committed fixture cache — the demo default.
    live_mode: bool = False

    cors_origins: str = "http://localhost"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # values come from the environment
