"""Application settings, loaded from the environment.

Only settings the code actually uses are declared. Unknown variables in .env are ignored,
so .env.example can stay ahead of the code as later phases land.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Values that have appeared in example files and tutorials. Not an exhaustive list — the
# variety check below catches the rest of the obvious ones.
_WEAK_SECRETS = frozenset(
    {
        "change-me",
        "changeme",
        "secret",
        "development",
        "test-secret-key-not-used-outside-tests-0123456789",
    }
)


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

    # Live network retrieval is the product default. Set LIVE_MODE=false explicitly for
    # the deterministic offline walkthrough and fixture tests.
    live_mode: bool = True

    trongrid_base_url: str = "https://api.trongrid.io"
    trongrid_api_key: str = ""
    etherscan_base_url: str = "https://api.etherscan.io/api"
    etherscan_api_key: str = ""
    blockscout_base_url: str = "https://eth.blockscout.com"

    # Measured 2026-09-05 (docs/research/OQ-01-provider-rate-limits.md). TronGrid meters
    # per RPC method with no burst tolerance: 2.0s spacing succeeded 100% of the time,
    # 1.2s only 67%. Buckets are per method, so the aggregate rate is higher than this.
    trongrid_rate_per_second: float = 0.5
    # Blockscout showed no throttling across 195 requests up to 11.8/s; kept conservative.
    blockscout_rate_per_second: float = 5.0
    # Etherscan now rejects keyless requests entirely, so this only applies with a key.
    etherscan_rate_per_second: float = 4.0

    http_timeout_seconds: float = 30.0
    http_max_retries: int = 3
    # The single highest-leverage performance lever: a closed block range never changes,
    # so re-fetching it is pure waste. 24h.
    cache_ttl_seconds: int = 86_400

    # An address with more transfers than this is almost certainly a service; the
    # truncation flag feeds attribution as a positive signal rather than being a failure.
    max_transfers_per_address: int = 10_000
    max_pages_per_fetch: int = 200
    page_size: int = 200

    cors_origins: str = "http://localhost"

    # Defaults tuned to the measured provider rates: at 0.5 req/s per TronGrid method,
    # 120s buys roughly 60 uncached addresses. Depth 5 / fan-out 20 is the design target
    # and remains available; these are what fits the time budget on a cold cache.
    trace_max_depth: int = 3
    trace_taint_threshold: float = 0.01
    trace_edge_budget: int = 5000
    trace_fanout_cap: int = 8
    # Hard ceiling on uncached addresses per trace, so a run cannot silently overrun.
    trace_address_budget: int = 60
    graph_node_cap: int = 500

    # Repository-relative by default so a fresh clone works with no setup — the same
    # reason LIVE_MODE is false. The container overrides both to /data/... where a
    # volume is mounted; see .env.example and docker-compose.yml.
    # Inbound request limiting. Off in tests, which would otherwise exhaust a shared
    # bucket and fail unrelated suites.
    rate_limit_enabled: bool = True
    # Only enable behind a load balancer that overwrites X-Forwarded-For. In front of
    # one, an attacker sets the header themselves and gets a fresh rate-limit bucket per
    # request.
    trust_proxy_headers: bool = False

    evidence_storage_path: str = "var/evidence"
    report_storage_path: str = "var/reports"
    # Located by search, not by counting `..` from __file__: a container puts these
    # beside the working directory, a checkout puts them above the package.
    fixture_path: str = "tests/fixtures/chain_data"
    risk_config_path: str = "config/risk_weights.yaml"
    label_data_path: str = "data/labels"

    @model_validator(mode="after")
    def _production_is_hardened(self) -> "Settings":
        """Refuse to start a production instance on a development configuration.

        Each of these is a mistake that is invisible until it is exploited, and each is
        made by deploying with a `.env` that was fine on a laptop. Failing at boot is the
        only failure mode that gets noticed.
        """
        if self.environment != "production":
            return self

        problems = []
        if self.secret_key in _WEAK_SECRETS or self.secret_key.startswith("change"):
            problems.append("SECRET_KEY is a placeholder value")
        if len(set(self.secret_key)) < 8:
            problems.append("SECRET_KEY has too little variety to be randomly generated")
        insecure = [o for o in self.cors_origin_list if o.startswith("http://")]
        if insecure:
            problems.append(f"CORS_ORIGINS contains plain-HTTP origins: {', '.join(insecure)}")
        if "*" in self.cors_origin_list:
            # With allow_credentials, a wildcard origin would hand any site the session.
            problems.append("CORS_ORIGINS contains a wildcard")
        if not self.rate_limit_enabled:
            problems.append("RATE_LIMIT_ENABLED is false")
        if "localhost" in self.database_url or "localhost" in self.redis_url:
            problems.append("DATABASE_URL or REDIS_URL still points at localhost")

        if problems:
            raise ValueError(
                "Refusing to start in production with an unsafe configuration: "
                + "; ".join(problems)
            )
        return self

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
