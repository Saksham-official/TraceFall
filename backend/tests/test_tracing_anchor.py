"""Anchoring to the victim's actual transaction.

The difference between an anchored and an unanchored trace is large, which is why the
intake form presses for the amount and time (FR-41).
"""

from datetime import timedelta
from decimal import Decimal

from app.tracing.anchor import resolve
from tests.tracing_fixtures import BASE_TIME, tx


def _inbound() -> list:
    return [
        tx("VICTIM", "A", 40_000_000_000, 0),  # 40,000 USDT
        tx("OTHER", "A", 15_000_000_000, 30),  # 15,000 USDT
        tx("THIRD", "A", 40_100_000_000, 60 * 72),  # 40,100 USDT, three days later
    ]


def test_exact_amount_and_time_anchors() -> None:
    result = resolve(_inbound(), "A", Decimal("40000"), BASE_TIME)
    assert result.anchored
    assert result.transfer is not None
    assert result.transfer.from_address == "VICTIM"
    assert result.reason == "ANCHORED"


def test_amount_within_tolerance_still_matches() -> None:
    """Fees change amounts and complainants round. A tight match loses real cases."""
    result = resolve(_inbound(), "A", Decimal("40500"), BASE_TIME)
    assert result.anchored


def test_amount_outside_tolerance_does_not_match() -> None:
    result = resolve(_inbound(), "A", Decimal("48000"), BASE_TIME)
    assert not result.anchored
    assert result.reason == "NO_MATCHING_TRANSFER"


def test_several_candidates_are_returned_rather_than_guessed() -> None:
    """Silently anchoring to the wrong transfer corrupts the whole trace while looking
    perfectly fine."""
    transfers = [
        tx("VICTIM", "A", 40_000_000_000, 0),
        tx("SOMEONE", "A", 40_000_000_000, 120),
    ]
    result = resolve(transfers, "A", Decimal("40000"), BASE_TIME)
    assert not result.anchored
    assert result.reason == "MULTIPLE_CANDIDATES"
    assert len(result.candidates) == 2


def test_a_wrong_timezone_does_not_discard_a_lone_amount_match() -> None:
    """Screenshots carry local time. Time narrows the field; it does not veto.

    With one amount match and a badly wrong time, we still anchor. With several matches
    a wrong time cannot disambiguate, so the candidates go back to the investigator —
    that case is covered separately.
    """
    transfers = [
        tx("VICTIM", "A", 40_000_000_000, 0),
        tx("OTHER", "A", 15_000_000_000, 30),
    ]
    result = resolve(transfers, "A", Decimal("40000"), BASE_TIME + timedelta(days=30))
    assert result.anchored
    assert result.transfer is not None
    assert result.transfer.from_address == "VICTIM"


def test_a_wrong_time_cannot_disambiguate_tied_amounts() -> None:
    result = resolve(_inbound(), "A", Decimal("40000"), BASE_TIME + timedelta(days=30))
    assert not result.anchored
    assert result.reason == "MULTIPLE_CANDIDATES"


def test_time_disambiguates_when_amounts_tie() -> None:
    transfers = [
        tx("VICTIM", "A", 40_000_000_000, 0),
        tx("SOMEONE", "A", 40_000_000_000, 60 * 24 * 10),
    ]
    result = resolve(transfers, "A", Decimal("40000"), BASE_TIME)
    assert result.anchored
    assert result.transfer is not None
    assert result.transfer.from_address == "VICTIM"


def test_no_reported_amount_means_no_anchor() -> None:
    result = resolve(_inbound(), "A", None, BASE_TIME)
    assert not result.anchored
    assert result.reason == "NO_AMOUNT_REPORTED"


def test_outbound_transfers_are_never_anchor_candidates() -> None:
    transfers = [tx("A", "SOMEWHERE", 40_000_000_000, 0)]
    result = resolve(transfers, "A", Decimal("40000"), BASE_TIME)
    assert not result.anchored


def test_unknown_decimals_cannot_match_an_amount() -> None:
    """Matching a reported 40,000 against a raw integer of unknown scale would be a guess."""
    transfers = [tx("VICTIM", "A", 40_000_000_000, 0, decimals=None)]
    result = resolve(transfers, "A", Decimal("40000"), BASE_TIME)
    assert not result.anchored


def test_a_lookalike_token_cannot_capture_the_anchor() -> None:
    """Real captured data contains a "USDTT" token beside genuine USDT. Nothing stops a
    scam token from claiming the symbol exactly, so a symbol match across two contracts
    must not be resolved silently."""
    genuine = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
    lookalike = "TGXjZQCTdH6ioWL3acappQEzo6sEPhCsGy"
    transfers = [
        tx("VICTIM", "A", 40_000_000_000, 0, contract=genuine),
        tx("POISONER", "A", 40_000_000_000, 5, contract=lookalike),
    ]
    for t in transfers:
        object.__setattr__(t, "asset_symbol", "USDT")

    result = resolve(transfers, "A", Decimal("40000"), BASE_TIME, asset_symbol="USDT")
    assert not result.anchored
    assert result.reason == "AMBIGUOUS_TOKEN_SYMBOL"
    assert len(result.candidates) == 2


def test_a_single_contract_still_anchors_when_a_symbol_is_given() -> None:
    genuine = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
    transfers = [tx("VICTIM", "A", 40_000_000_000, 0, contract=genuine)]
    object.__setattr__(transfers[0], "asset_symbol", "USDT")
    result = resolve(transfers, "A", Decimal("40000"), BASE_TIME, asset_symbol="USDT")
    assert result.anchored
