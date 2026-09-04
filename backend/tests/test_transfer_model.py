"""The canonical transfer, which every engine downstream depends on."""

from datetime import UTC, datetime
from decimal import Decimal

from app.db.models.enums import ChainCode, TransferStatus
from app.normalize.transfer import NormalizedTransfer


def _transfer(**overrides: object) -> NormalizedTransfer:
    defaults: dict = {
        "chain": ChainCode.TRON,
        "tx_hash": "a" * 64,
        "transfer_index": 0,
        "block_number": 1,
        "block_time": datetime(2026, 8, 14, 9, 32, tzinfo=UTC),
        "from_address": "TFrom",
        "to_address": "TTo",
        "amount_raw": 40_000_000_000,
        "status": TransferStatus.SUCCESS,
    }
    defaults.update(overrides)
    return NormalizedTransfer(**defaults)


def test_six_decimal_token_converts_correctly() -> None:
    assert _transfer(decimals=6).amount == Decimal("40000")


def test_eighteen_decimal_token_converts_correctly() -> None:
    assert _transfer(amount_raw=10**18, decimals=18).amount == Decimal("1")


def test_unknown_decimals_suppress_the_amount_rather_than_guessing() -> None:
    """Showing a 6-decimal token as an 18-decimal one understates it by a trillion."""
    transfer = _transfer(decimals=None)
    assert transfer.amount is None
    assert transfer.amount_raw == 40_000_000_000


def test_very_large_amounts_stay_exact() -> None:
    huge = 2**200 + 1
    assert _transfer(amount_raw=huge).amount_raw == huge


def test_amount_is_never_a_float() -> None:
    assert isinstance(_transfer(decimals=6).amount, Decimal)
    assert isinstance(_transfer().amount_raw, int)


def test_identity_is_the_idempotency_key() -> None:
    a = _transfer()
    b = _transfer(amount_raw=999)  # same identity, different payload
    assert a.identity == b.identity
    assert _transfer(transfer_index=1).identity != a.identity


def test_asset_key_separates_native_from_tokens() -> None:
    native = _transfer()
    token = _transfer(asset_contract="TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t")
    assert native.asset_key != token.asset_key
    assert native.asset_key.endswith("native")


def test_failed_transfers_are_representable_and_flagged() -> None:
    """A scammer's failed transaction reveals intent, destination and timing."""
    failed = _transfer(status=TransferStatus.FAILED)
    assert not failed.succeeded
    assert failed.amount_raw > 0


def test_transfers_are_immutable() -> None:
    import pytest

    with pytest.raises(Exception):  # noqa: B017  # frozen dataclass
        _transfer().amount_raw = 1  # type: ignore[misc]
