"""The chain adapter boundary.

All chain-specific code lives behind this interface. Adding a chain means adding one
module here and changing nothing in tracing, graph, risk, reports, or the UI (NFR-17).

Phase 2 implements address validation only; retrieval lands in Phase 3.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Protocol

from app.db.models.enums import ChainCode


class InvalidAddressError(ValueError):
    """Raised with a message an investigator can act on, not just 'invalid'."""


@dataclass(frozen=True)
class ValidatedAddress:
    chain: ChainCode
    # Canonical storage form: TRON base58 as-is, Ethereum lowercase hex.
    canonical: str
    # Form shown to the user: Ethereum gets its EIP-55 checksum casing back.
    display: str


class ChainAdapter(Protocol):
    code: ChainCode

    def validate_address(self, address: str) -> ValidatedAddress: ...

    def looks_like(self, address: str) -> bool:
        """Cheap format sniff used for chain auto-detection, without full validation."""
        ...


@dataclass(frozen=True)
class TimeWindow:
    """Analysis window. Only transfers inside it are eligible for tracing (FR-50)."""

    start: datetime
    end: datetime

    @classmethod
    def last_days(cls, days: int, now: datetime | None = None) -> "TimeWindow":
        end = now or datetime.now(UTC)
        return cls(start=end - timedelta(days=days), end=end)

    @property
    def start_ms(self) -> int:
        return int(self.start.timestamp() * 1000)

    @property
    def end_ms(self) -> int:
        return int(self.end.timestamp() * 1000)

    def contains_epoch_seconds(self, seconds: int | str) -> bool:
        return self.start.timestamp() <= int(seconds) <= self.end.timestamp()


@dataclass(frozen=True)
class RawResponse:
    """A provider response, exactly as received.

    Persisted before any parsing (FR-22), so a parse failure never loses the evidence
    that would explain it.
    """

    provider: str
    endpoint: str
    params: dict[str, Any]
    status: int
    body: bytes
    retrieved_at: datetime
    from_cache: bool = False
    is_fixture: bool = False

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.body).hexdigest()

    def json(self) -> Any:
        try:
            return json.loads(self.body)
        except json.JSONDecodeError as exc:
            raise ProviderParseError(
                f"{self.provider} returned a body that is not valid JSON"
            ) from exc


class TruncationReason(StrEnum):
    PAGE_LIMIT = "PAGE_LIMIT"
    TRANSFER_LIMIT = "TRANSFER_LIMIT"
    TIME_WINDOW = "TIME_WINDOW"
    PROVIDER_ERROR = "PROVIDER_ERROR"


@dataclass
class FetchResult:
    """Retrieval never silently returns a smaller answer.

    `complete=False` with a reason is a valid result that propagates all the way to the
    investigator; raising would lose the partial data we did obtain (FR-25).
    """

    responses: list[RawResponse] = field(default_factory=list)
    record_count: int = 0
    complete: bool = True
    truncation_reason: TruncationReason | None = None
    provider_used: str | None = None

    def truncate(self, reason: TruncationReason) -> "FetchResult":
        self.complete = False
        self.truncation_reason = reason
        return self


class ProviderError(Exception):
    """Base for upstream failures. Never escapes the ingestion service."""


class ProviderUnavailable(ProviderError):
    """Provider unreachable, timed out, or returned 5xx after retries."""


class ProviderRateLimited(ProviderError):
    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class ProviderParseError(ProviderError):
    """Response arrived but did not have the expected shape."""
