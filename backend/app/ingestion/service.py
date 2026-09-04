"""Blockchain Data Service.

Orchestrates retrieval across chain adapters and records evidence. This is the boundary
where provider failure stops being an exception and becomes a partial result: the
analysis completes with what was obtained, explicitly marked (FR-25).
"""

import logging
import uuid
from collections.abc import Awaitable
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.chains import ethereum, tron
from app.chains.base import FetchResult, ProviderError, RawResponse, TimeWindow
from app.db.models.enums import ChainCode
from app.ingestion import evidence
from app.ingestion.fixtures import FixtureMissing

log = logging.getLogger(__name__)


@dataclass
class AddressData:
    """Everything retrieved for one address, with its completeness stated."""

    chain: ChainCode
    address: str
    native: FetchResult
    token: FetchResult
    internal: FetchResult | None = None
    degradations: list[str] = field(default_factory=list)

    @property
    def responses(self) -> list[RawResponse]:
        parts = [self.native, self.token] + ([self.internal] if self.internal else [])
        return [r for part in parts for r in part.responses]

    @property
    def record_count(self) -> int:
        parts = [self.native, self.token] + ([self.internal] if self.internal else [])
        return sum(part.record_count for part in parts)

    @property
    def complete(self) -> bool:
        parts = [self.native, self.token] + ([self.internal] if self.internal else [])
        return all(part.complete for part in parts) and not self.degradations

    @property
    def truncation_reasons(self) -> list[str]:
        parts = [self.native, self.token] + ([self.internal] if self.internal else [])
        return [str(p.truncation_reason) for p in parts if p.truncation_reason]

    @property
    def is_fixture(self) -> bool:
        return any(r.is_fixture for r in self.responses)


async def _safe(label: str, coro: Awaitable[FetchResult], degradations: list[str]) -> FetchResult:
    """Provider failure degrades the result; it never escapes this service."""
    try:
        return await coro
    except FixtureMissing:
        # Distinct from a provider failure: a missing fixture is an operator error, and
        # silently returning empty would look like an address with no activity.
        raise
    except ProviderError as exc:
        log.warning("%s retrieval degraded: %s", label, exc)
        degradations.append(f"{label}: {exc}")
        return FetchResult(complete=False)


async def retrieve_address(
    chain: ChainCode,
    address: str,
    window: TimeWindow | None = None,
    session: AsyncSession | None = None,
    case_id: uuid.UUID | None = None,
    analysis_run_id: uuid.UUID | None = None,
) -> AddressData:
    """Retrieve an address's public transaction record and record it as evidence."""
    degradations: list[str] = []

    if chain is ChainCode.TRON:
        # Token transfers first: the fraud money is TRC-20 USDT, not TRX.
        token = await _safe("tron.token", tron.fetch_token_transfers(address, window), degradations)
        native = await _safe(
            "tron.native", tron.fetch_native_transfers(address, window), degradations
        )
        data = AddressData(chain=chain, address=address, native=native, token=token)
    else:
        token = await _safe(
            "ethereum.token", ethereum.fetch_token_transfers(address, window), degradations
        )
        native = await _safe(
            "ethereum.native", ethereum.fetch_native_transfers(address, window), degradations
        )
        internal = await _safe(
            "ethereum.internal", ethereum.fetch_internal_transfers(address, window), degradations
        )
        data = AddressData(
            chain=chain, address=address, native=native, token=token, internal=internal
        )

    data.degradations = degradations

    if session is not None:
        for response in data.responses:
            await evidence.record(session, response, case_id, analysis_run_id)
        await session.commit()

    log.info(
        "retrieved %s %s: %d records, complete=%s%s",
        chain,
        address,
        data.record_count,
        data.complete,
        f", truncated={data.truncation_reasons}" if data.truncation_reasons else "",
    )
    return data
