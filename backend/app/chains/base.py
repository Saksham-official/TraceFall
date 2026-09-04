"""The chain adapter boundary.

All chain-specific code lives behind this interface. Adding a chain means adding one
module here and changing nothing in tracing, graph, risk, reports, or the UI (NFR-17).

Phase 2 implements address validation only; retrieval lands in Phase 3.
"""

from dataclasses import dataclass
from typing import Protocol

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
