"""Application settings, loaded from the environment.

Only settings the code actually uses are declared. Unknown variables in .env are ignored,
so .env.example can stay ahead of the code as later phases land.
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

    database_url: str = "postgresql+asyncpg://tracefall:tracefall@localhost:5432/tracefall"
    redis_url: str = "redis://localhost:6379/0"

    access_token_minutes: int = 15
    refresh_token_days: int = 7
    jwt_algorithm: str = "HS256"

    # false serves everything from the committed fixture cache — the demo default.
    live_mode: bool = False

    cors_origins: str = "http://localhost"

    trace_max_depth: int = 5
    trace_taint_threshold: float = 0.01
    trace_edge_budget: int = 5000
    trace_fanout_cap: int = 20
    graph_node_cap: int = 500

    evidence_storage_path: str = "/data/evidence"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def sync_database_url(self) -> str:
        """Alembic runs synchronously; strip the async driver."""
        return self.database_url.replace("+asyncpg", "")


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # values come from the environment
