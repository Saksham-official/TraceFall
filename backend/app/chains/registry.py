from collections.abc import Callable

from app.chains import ethereum, tron
from app.chains.base import ChainAdapter, InvalidAddressError, ValidatedAddress
from app.db.models.enums import ChainCode

ADAPTERS: dict[ChainCode, ChainAdapter] = {
    ChainCode.TRON: tron.adapter,
    ChainCode.ETHEREUM: ethereum.adapter,
}

# Recognised but unsupported formats, so we can say something more useful than "invalid".
_UNSUPPORTED_HINTS: tuple[tuple[Callable[[str], bool], str], ...] = (
    (lambda a: a.startswith(("bc1", "1", "3")) and 26 <= len(a) <= 62, "Bitcoin"),
    (lambda a: len(a) in range(32, 45) and a.isalnum() and not a.startswith("0x"), "Solana"),
)


def get_adapter(chain: ChainCode) -> ChainAdapter:
    return ADAPTERS[chain]


def detect_chain(address: str) -> ChainCode | None:
    address = address.strip()
    for code, adapter in ADAPTERS.items():
        if adapter.looks_like(address):
            return code
    return None


def unsupported_hint(address: str) -> str | None:
    address = address.strip()
    for matches, name in _UNSUPPORTED_HINTS:
        if matches(address):
            return name
    return None


def validate(address: str, chain: ChainCode | None = None) -> ValidatedAddress:
    """Validate before any network call (FR-12)."""
    address = address.strip()
    if not address:
        raise InvalidAddressError("Address is empty")

    if chain is None:
        chain = detect_chain(address)
    if chain is None:
        hint = unsupported_hint(address)
        if hint:
            raise InvalidAddressError(
                f"This looks like a {hint} address. TraceFall currently supports TRON and Ethereum."
            )
        raise InvalidAddressError(
            "Address format not recognised. TraceFall currently supports TRON and Ethereum."
        )
    return get_adapter(chain).validate_address(address)
