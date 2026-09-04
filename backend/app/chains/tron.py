"""TRON address validation.

base58check: 34 characters starting with T, decoding to a 0x41 version byte, a 20-byte
address, and a 4-byte double-SHA256 checksum.
"""

import hashlib
from typing import Any

from app.chains.base import (
    ChainAdapter,
    FetchResult,
    InvalidAddressError,
    TimeWindow,
    TruncationReason,
    ValidatedAddress,
)
from app.core.config import get_settings
from app.db.models.enums import ChainCode
from app.ingestion import gateway

_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_INDEX = {c: i for i, c in enumerate(_ALPHABET)}

MAINNET_PREFIX = 0x41
ADDRESS_LENGTH = 34
DECODED_LENGTH = 25


def b58decode(value: str) -> bytes:
    number = 0
    for char in value:
        if char not in _INDEX:
            raise InvalidAddressError(f"'{char}' is not a valid base58 character")
        number = number * 58 + _INDEX[char]
    raw = number.to_bytes((number.bit_length() + 7) // 8, "big")
    # Leading '1's encode leading zero bytes.
    pad = len(value) - len(value.lstrip("1"))
    return b"\x00" * pad + raw


def b58encode(raw: bytes) -> str:
    number = int.from_bytes(raw, "big")
    out = ""
    while number:
        number, rem = divmod(number, 58)
        out = _ALPHABET[rem] + out
    pad = len(raw) - len(raw.lstrip(b"\x00"))
    return "1" * pad + out


def _checksum(payload: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]


class TronAdapter:
    code = ChainCode.TRON

    def looks_like(self, address: str) -> bool:
        # A sniff, not validation: a near-miss must still route here so the user gets
        # "a TRON address is 34 characters" rather than "format not recognised".
        return address.startswith("T") and 30 <= len(address) <= 40

    def validate_address(self, address: str) -> ValidatedAddress:
        address = address.strip()
        if not address.startswith("T"):
            raise InvalidAddressError("A TRON address starts with 'T'")
        if len(address) != ADDRESS_LENGTH:
            raise InvalidAddressError(
                f"A TRON address is {ADDRESS_LENGTH} characters; this one is {len(address)}"
            )

        decoded = b58decode(address)
        if len(decoded) != DECODED_LENGTH:
            raise InvalidAddressError("Address does not decode to a valid TRON address")
        if decoded[0] != MAINNET_PREFIX:
            raise InvalidAddressError("Address is not a TRON mainnet address")
        if _checksum(decoded[:21]) != decoded[21:]:
            raise InvalidAddressError(
                "Checksum does not match — the address may have been mistyped"
            )
        return ValidatedAddress(chain=ChainCode.TRON, canonical=address, display=address)

    def to_hex(self, address: str) -> str:
        """Internal hex form some TRON endpoints use. Confined to this adapter."""
        return b58decode(self.validate_address(address).canonical)[:21].hex()

    def from_hex(self, hex_address: str) -> str:
        raw = bytes.fromhex(hex_address.removeprefix("0x"))
        return b58encode(raw + _checksum(raw))


adapter: ChainAdapter = TronAdapter()


# --- Retrieval -------------------------------------------------------------------

PROVIDER = "trongrid"


def _headers() -> dict[str, str]:
    key = get_settings().trongrid_api_key
    return {"TRON-PRO-API-KEY": key} if key else {}


async def _paginate(path: str, address: str, window: TimeWindow | None) -> FetchResult:
    """Walk TronGrid's fingerprint pagination until a cap or the end of the data."""
    settings = get_settings()
    url = f"{settings.trongrid_base_url}{path.format(address=address)}"
    result = FetchResult(provider_used=PROVIDER)
    params: dict[str, Any] = {"limit": settings.page_size, "order_by": "block_timestamp,desc"}
    if window is not None:
        params["min_timestamp"] = window.start_ms
        params["max_timestamp"] = window.end_ms

    # TronGrid meters each RPC method independently, so the bucket is the path template.
    method = path.rsplit("/", 1)[-1] or "transactions"

    for page in range(settings.max_pages_per_fetch):
        response = await gateway.request(
            PROVIDER, url, dict(params), settings.trongrid_rate_per_second, _headers(), method
        )
        result.responses.append(response)
        payload = response.json()
        rows = payload.get("data") or []
        result.record_count += len(rows)

        if result.record_count >= settings.max_transfers_per_address:
            # Itself a finding: an address this active is almost certainly a service.
            return result.truncate(TruncationReason.TRANSFER_LIMIT)

        fingerprint = (payload.get("meta") or {}).get("fingerprint")
        if not rows or not fingerprint:
            return result
        params["fingerprint"] = fingerprint
        if page == settings.max_pages_per_fetch - 1:
            return result.truncate(TruncationReason.PAGE_LIMIT)

    return result


async def fetch_native_transfers(address: str, window: TimeWindow | None = None) -> FetchResult:
    return await _paginate("/v1/accounts/{address}/transactions", address, window)


async def fetch_token_transfers(address: str, window: TimeWindow | None = None) -> FetchResult:
    """TRC-20 first: a USDT fraud traced via TRX transfers starts with the noise."""
    return await _paginate("/v1/accounts/{address}/transactions/trc20", address, window)


async def fetch_account(address: str) -> FetchResult:
    settings = get_settings()
    url = f"{settings.trongrid_base_url}/v1/accounts/{address}"
    response = await gateway.request(
        PROVIDER, url, {}, settings.trongrid_rate_per_second, _headers(), "accounts"
    )
    return FetchResult(responses=[response], record_count=1, provider_used=PROVIDER)
