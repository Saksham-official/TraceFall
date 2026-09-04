"""Address validation is a security control: address strings flow into database queries,
external API calls, and file paths."""

import pytest

from app.chains.base import InvalidAddressError
from app.chains.ethereum import to_checksum_address
from app.chains.registry import detect_chain, validate
from app.chains.tron import TronAdapter
from app.db.models.enums import ChainCode

# Real, well-known public contract addresses, used purely as format fixtures.
USDT_TRC20 = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
USDT_ERC20 = "0xdAC17F958D2ee523a2206206994597C13D831ec7"


@pytest.mark.parametrize(
    ("address", "chain"),
    [
        (USDT_TRC20, ChainCode.TRON),
        (USDT_ERC20, ChainCode.ETHEREUM),
        (USDT_ERC20.lower(), ChainCode.ETHEREUM),
        (USDT_ERC20.upper().replace("0X", "0x"), ChainCode.ETHEREUM),
    ],
)
def test_valid_addresses_are_accepted(address: str, chain: ChainCode) -> None:
    assert validate(address).chain == chain


@pytest.mark.parametrize(
    ("address", "expected_message"),
    [
        ("TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6X", "Checksum"),
        ("0xdAC17F958D2ee523a2206206994597C13D831ec8", "checksum"),
        ("TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjL", "34 characters"),
        ("0xdac17f958d2ee523", "not recognised"),
        ("0xdAC17F958D2ee523a2206206994597C13D831ecZ", "hexadecimal"),
        ("", "empty"),
    ],
)
def test_invalid_addresses_are_rejected(address: str, expected_message: str) -> None:
    with pytest.raises(InvalidAddressError, match=expected_message):
        validate(address)


def test_bitcoin_address_gets_a_useful_message() -> None:
    """ "Invalid address" is useless; naming the chain we detected is not."""
    with pytest.raises(InvalidAddressError, match="Bitcoin"):
        validate("1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa")


def test_ethereum_canonicalises_to_lowercase_and_displays_checksummed() -> None:
    validated = validate(USDT_ERC20)
    assert validated.canonical == USDT_ERC20.lower()
    assert validated.display == USDT_ERC20


def test_all_case_variants_resolve_to_one_canonical_form() -> None:
    forms = [USDT_ERC20, USDT_ERC20.lower(), USDT_ERC20.upper().replace("0X", "0x")]
    assert len({validate(f).canonical for f in forms}) == 1


def test_eip55_checksum_matches_the_reference_implementation() -> None:
    assert to_checksum_address(USDT_ERC20.lower()) == USDT_ERC20


def test_chain_autodetection() -> None:
    assert detect_chain(USDT_TRC20) == ChainCode.TRON
    assert detect_chain(USDT_ERC20) == ChainCode.ETHEREUM
    assert detect_chain("nonsense") is None


def test_tron_hex_conversion_round_trips() -> None:
    adapter = TronAdapter()
    assert adapter.from_hex(adapter.to_hex(USDT_TRC20)) == USDT_TRC20
