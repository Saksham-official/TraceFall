"""Ethereum address validation.

Mixed-case addresses carry an EIP-55 checksum, which is verified — that check catches
real transcription errors from victim statements, which is exactly the input this system
receives. All-lower and all-upper addresses assert no checksum and are accepted.
"""

import re

from Crypto.Hash import keccak

from app.chains.base import ChainAdapter, InvalidAddressError, ValidatedAddress
from app.db.models.enums import ChainCode

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
