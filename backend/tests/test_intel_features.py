"""Behavioural feature extraction.

These numbers decide whether an address is called a deposit address, and a deposit
address is what a freeze request is sent about. Every signal is checked against a
hand-built graph whose expected value can be computed by eye.
"""

from fractions import Fraction

from app.db.models.enums import TransferStatus
from app.intel.features import extract
from tests.tracing_fixtures import tx

DEPOSIT = "TDeposit"
HOT = "THotWallet"
OTHER = "TSomewhereElse"
SENDERS = [f"TSender{i}" for i in range(5)]


def deposit_address_transfers() -> list:
    """The textbook shape: many senders in, everything swept to one destination."""
    transfers = []
    for i, sender in enumerate(SENDERS):
        minute = i * 60
        transfers.append(tx(sender, DEPOSIT, 1_000_000, minutes=minute))
        transfers.append(tx(DEPOSIT, HOT, 1_000_000, minutes=minute + 10))
    return transfers


def test_deposit_address_shape_is_measured_correctly() -> None:
    features = extract(DEPOSIT, deposit_address_transfers())

    assert features.tx_count_in == 5
    assert features.tx_count_out == 5
    assert features.counterparty_diversity_in == 5
    assert features.counterparty_diversity_out == 1
    assert features.sweep_consistency == Fraction(1)
    assert features.sweep_ratio == Fraction(1)
    assert features.balance_retention == Fraction(0)
    assert features.median_dwell_seconds == 600
    assert features.dominant_out_destination == HOT
    assert features.initiates_transfers is False
    assert features.has_sufficient_activity is True


def test_a_personal_wallet_does_not_look_like_a_deposit_address() -> None:
    """Spends to several destinations, keeps a balance, waits days."""
    transfers = [
        tx(SENDERS[0], OTHER, 10_000_000, minutes=0),
        tx(OTHER, SENDERS[1], 1_000_000, minutes=4_320),
        tx(OTHER, SENDERS[2], 1_000_000, minutes=8_640),
        tx(OTHER, SENDERS[3], 1_000_000, minutes=12_960),
    ]
    features = extract(OTHER, transfers)

    assert features.counterparty_diversity_out == 3
    assert features.sweep_consistency == Fraction(1, 3)
    assert features.balance_retention == Fraction(7, 10)
    assert features.median_dwell_seconds == 8_640 * 60


def test_ratios_are_exact_fractions_not_floats() -> None:
    """A ratio that reaches a police report is computed exactly, then rounded once."""
    transfers = [
        tx(SENDERS[0], DEPOSIT, 3, minutes=0),
        tx(DEPOSIT, HOT, 1, minutes=1),
        tx(DEPOSIT, OTHER, 1, minutes=2),
    ]
    features = extract(DEPOSIT, transfers)

    assert features.sweep_consistency == Fraction(1, 2)
    assert isinstance(features.sweep_consistency, Fraction)
    assert features.balance_retention == Fraction(1, 3)
    # The exact third survives; a float would have lost it here.
    assert features.balance_retention * 3 == Fraction(1)


def test_failed_transfers_describe_no_behaviour() -> None:
    """Retained as evidence of an attempt, excluded from what the address *did*."""
    transfers = deposit_address_transfers()
    transfers.append(tx(DEPOSIT, OTHER, 500_000_000, minutes=1, status=TransferStatus.FAILED))

    features = extract(DEPOSIT, transfers)

    assert features.counterparty_diversity_out == 1
    assert features.sweep_consistency == Fraction(1)


def test_value_signals_are_scoped_to_one_asset() -> None:
    """Raw amounts across assets are not comparable, so they are never pooled."""
    transfers = deposit_address_transfers()
    # One TRX movement at 18-decimal scale would swamp every USDT ratio if pooled.
    transfers.append(tx(DEPOSIT, OTHER, 10**18, minutes=5, contract=None, decimals=6))

    features = extract(DEPOSIT, transfers)

    assert features.asset_key.endswith("TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t")
    assert features.sweep_consistency == Fraction(1)
    assert features.distinct_assets == 2


def test_an_address_that_spends_before_receiving_initiates_transfers() -> None:
    transfers = [
        tx(OTHER, SENDERS[0], 1_000, minutes=0),
        tx(SENDERS[1], OTHER, 5_000, minutes=10),
        tx(OTHER, SENDERS[0], 1_000, minutes=20),
    ]
    assert extract(OTHER, transfers).initiates_transfers is True
    assert extract(DEPOSIT, deposit_address_transfers()).initiates_transfers is False


def test_unmeasurable_signals_are_none_not_zero() -> None:
    """`None` means not measured. Zero would be a claim we did not make."""
    features = extract(OTHER, [tx(SENDERS[0], OTHER, 1_000, minutes=0)])

    assert features.sweep_consistency is None
    assert features.sweep_ratio is None
    assert features.median_dwell_seconds is None
    assert features.dominant_out_destination is None
    assert features.contract_interaction_rate is None
    assert features.balance_retention == Fraction(1)
    assert features.has_sufficient_activity is False


def test_an_address_with_no_transfers_measures_nothing() -> None:
    features = extract(OTHER, [])

    assert features.asset_key is None
    assert features.tx_count_in == 0
    assert features.balance_retention is None
    assert features.has_sufficient_activity is False


def test_sweep_ratio_never_exceeds_one_on_partial_data() -> None:
    """Retrieval may miss earlier receipts. The ratio clamps rather than reporting 300%."""
    transfers = [
        tx(SENDERS[0], DEPOSIT, 100, minutes=0),
        tx(DEPOSIT, HOT, 300, minutes=5),
    ]
    assert extract(DEPOSIT, transfers).sweep_ratio == Fraction(1)


def test_dominant_destination_is_by_value_not_count() -> None:
    """One large sweep outweighs several small spends — that is where the money went."""
    transfers = [
        tx(SENDERS[0], DEPOSIT, 1_000_000, minutes=0),
        tx(DEPOSIT, OTHER, 1_000, minutes=1),
        tx(DEPOSIT, OTHER, 1_000, minutes=2),
        tx(DEPOSIT, HOT, 900_000, minutes=3),
    ]
    assert extract(DEPOSIT, transfers).dominant_out_destination == HOT
