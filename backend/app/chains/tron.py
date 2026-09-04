"""TRON address validation.

base58check: 34 characters starting with T, decoding to a 0x41 version byte, a 20-byte
address, and a 4-byte double-SHA256 checksum.
"""

import hashlib

from app.chains.base import ChainAdapter, InvalidAddressError, ValidatedAddress
from app.db.models.enums import ChainCode

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
