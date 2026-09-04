"""Ethereum address validation.

Mixed-case addresses carry an EIP-55 checksum, which is verified — that check catches
real transcription errors from victim statements, which is exactly the input this system
receives. All-lower and all-upper addresses assert no checksum and are accepted.
"""

import logging
import re
from typing import Any

from Crypto.Hash import keccak

from app.chains.base import (
    ChainAdapter,
    FetchResult,
    InvalidAddressError,
    ProviderError,
    ProviderParseError,
    ProviderRateLimited,
    ProviderUnavailable,
    TimeWindow,
    TruncationReason,
    ValidatedAddress,
)
from app.core.config import get_settings
from app.db.models.enums import ChainCode
from app.ingestion import gateway

log = logging.getLogger(__name__)

_HEX = re.compile(r"^0x[0-9a-fA-F]{40}$")
ADDRESS_LENGTH = 42


def keccak256(data: bytes) -> bytes:
    return keccak.new(data=data, digest_bits=256).digest()


def to_checksum_address(address: str) -> str:
    """EIP-55: uppercase a hex digit when the corresponding hash nibble is >= 8."""
    body = address.removeprefix("0x").lower()
    digest = keccak256(body.encode()).hex()
    return "0x" + "".join(
        char.upper() if char.isalpha() and int(digest[i], 16) >= 8 else char
        for i, char in enumerate(body)
    )


class EthereumAdapter:
    code = ChainCode.ETHEREUM

    def looks_like(self, address: str) -> bool:
        # A sniff, not validation — see the note in the TRON adapter.
        stripped = address.strip()
        return stripped.lower().startswith("0x") and 30 <= len(stripped) <= 50

    def validate_address(self, address: str) -> ValidatedAddress:
        address = address.strip()
        if not address.startswith("0x"):
            raise InvalidAddressError("An Ethereum address starts with '0x'")
        if len(address) != ADDRESS_LENGTH:
            raise InvalidAddressError(
                f"An Ethereum address is {ADDRESS_LENGTH} characters; this one is {len(address)}"
            )
        if not _HEX.match(address):
            raise InvalidAddressError("Address contains non-hexadecimal characters")

        body = address[2:]
        is_mixed_case = body != body.lower() and body != body.upper()
        if is_mixed_case and to_checksum_address(address) != address:
            raise InvalidAddressError(
                "This Ethereum address has an invalid checksum — it may have been mistyped"
            )

        canonical = address.lower()
        return ValidatedAddress(
            chain=ChainCode.ETHEREUM,
            canonical=canonical,
            display=to_checksum_address(canonical),
        )


adapter: ChainAdapter = EthereumAdapter()


# --- Retrieval -------------------------------------------------------------------

# Blockscout is primary: it needs no API key, measured ~20x faster than TronGrid, and
# Etherscan now rejects every keyless request outright. Etherscan is the failover, used
# when a key is configured.
PRIMARY = "blockscout"
FAILOVER = "etherscan"

# Blockscout implements the Etherscan API shape, so one parser serves both hosts.
_ACTIONS = {
    "native": "txlist",
    "internal": "txlistinternal",
    "token": "tokentx",
}


def _providers() -> list[tuple[str, str, str, float]]:
    """(name, base_url, api_key, rate) in preference order."""
    settings = get_settings()
    providers = [
        (
            PRIMARY,
            f"{settings.blockscout_base_url}/api",
            "",
            settings.blockscout_rate_per_second,
        )
    ]
    # Etherscan rejects keyless requests, so it is only worth trying with a key.
    if settings.etherscan_api_key:
        providers.append(
            (
                FAILOVER,
                settings.etherscan_base_url,
                settings.etherscan_api_key,
                settings.etherscan_rate_per_second,
            )
        )
    return providers


# Blockscout returns valid data alongside this notice while it is still indexing. Treating
# it as complete is exactly the silent-incompleteness failure internal transactions exist
# to prevent.
_INCOMPLETE_MARKERS = ("have not yet been processed", "not yet indexed")


def _check_payload(provider: str, payload: dict[str, Any]) -> tuple[list[dict[str, Any]], bool]:
    """Returns (rows, complete).

    Etherscan reports rate limiting as HTTP 200 with status "0", so transport-level retry
    never sees it. Blockscout reports partial indexing the same way — with usable rows
    attached, which is more dangerous because it looks like success.
    """
    status = str(payload.get("status", ""))
    message = str(payload.get("message", ""))
    result = payload.get("result")

    if isinstance(result, str) and "rate limit" in result.lower():
        raise ProviderRateLimited(f"{provider} rate limited: {result}")
    if isinstance(result, str) and "api key" in result.lower():
        raise ProviderUnavailable(f"{provider} requires an API key: {result}")

    complete = not any(marker in message.lower() for marker in _INCOMPLETE_MARKERS)

    if isinstance(result, list) and (status == "1" or not complete):
        return result, complete
    if "no transactions found" in message.lower():
        return [], True
    raise ProviderParseError(f"{provider} returned an unexpected payload: {message or result!r}")


async def _paginate(kind: str, address: str, window: TimeWindow | None) -> FetchResult:
    settings = get_settings()
    errors: list[str] = []

    for provider, base_url, api_key, rate in _providers():
        result = FetchResult(provider_used=provider)
        try:
            for page in range(1, settings.max_pages_per_fetch + 1):
                params: dict[str, Any] = {
                    "module": "account",
                    "action": _ACTIONS[kind],
                    "address": address,
                    "startblock": 0,
                    "endblock": 99_999_999,
                    "page": page,
                    "offset": settings.page_size,
                    "sort": "desc",
                }
                if api_key:
                    params["apikey"] = api_key

                response = await gateway.request(
                    provider, base_url, dict(params), rate, None, _ACTIONS[kind]
                )
                result.responses.append(response)
                rows, complete = _check_payload(provider, response.json())
                result.record_count += len(rows)
                if not complete:
                    # Usable rows, but the provider says its index is behind.
                    return result.truncate(TruncationReason.PROVIDER_ERROR)

                if result.record_count >= settings.max_transfers_per_address:
                    return result.truncate(TruncationReason.TRANSFER_LIMIT)
                if len(rows) < settings.page_size:
                    return result
                # Rows are newest-first, so once a page ends before the window there is
                # nothing older worth fetching.
                if window is not None and not window.contains_epoch_seconds(
                    rows[-1].get("timeStamp", 0)
                ):
                    return result
                if page == settings.max_pages_per_fetch:
                    return result.truncate(TruncationReason.PAGE_LIMIT)
            return result
        except ProviderError as exc:
            errors.append(f"{provider}: {exc}")
            log.warning("%s failed for %s, trying failover: %s", provider, address, exc)
            continue

    raise ProviderUnavailable("; ".join(errors) or "no Ethereum provider available")


async def fetch_native_transfers(address: str, window: TimeWindow | None = None) -> FetchResult:
    return await _paginate("native", address, window)


async def fetch_internal_transfers(address: str, window: TimeWindow | None = None) -> FetchResult:
    """Where contract-mediated value actually moves. Omitting these produces a trace that
    looks complete and is not."""
    return await _paginate("internal", address, window)


async def fetch_token_transfers(address: str, window: TimeWindow | None = None) -> FetchResult:
    return await _paginate("token", address, window)
