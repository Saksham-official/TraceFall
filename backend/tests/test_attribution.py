"""The attribution integrity suite — VASP_IDENTIFICATION.md sections 7 and 8.

This is the product's central claim, so these tests are about discipline rather than
arithmetic: that a guess is never presented as a fact, that a chain of inference cannot
produce more confidence than its weakest link, and that "we do not know" is a first-class
answer rather than a failure.
"""

from datetime import date
from fractions import Fraction

from app.attribution.decision import (
    CONFIDENCE_CAP,
    DEPOSIT_THRESHOLD,
    AttributionResult,
    Reason,
    decide,
    funnel_score,
)
from app.db.models.enums import AttributionMethod, AttributionTier, EntityType, LabelReliability
from app.intel.features import extract
from app.labels.matcher import AddressLabels, LabelMatch
from tests.test_intel_features import DEPOSIT, HOT, OTHER, SENDERS, deposit_address_transfers
from tests.tracing_fixtures import tx


def label(
    address: str = HOT,
    entity: str = "Binance",
    entity_type: EntityType = EntityType.EXCHANGE,
    source: str = "Curated exchange wallets",
    reliability: LabelReliability = LabelReliability.HIGH,
) -> LabelMatch:
    return LabelMatch(
        address=address,
        entity_id=1,
        entity_name=entity,
        entity_type=entity_type,
        label_text=f"{entity} hot wallet",
        source_name=source,
        source_url="https://example.test/dataset",
        dataset_date=date(2026, 7, 1),
        reliability=reliability,
    )


def labels(*matches: LabelMatch) -> AddressLabels:
    return AddressLabels(address=matches[0].address, matches=matches)


def deposit_features(address: str = DEPOSIT):  # type: ignore[no-untyped-def]
    return extract(address, deposit_address_transfers())


# --- Step 1: dataset match ---------------------------------------------------------


def test_dataset_match_is_confirmed_and_cites_its_source() -> None:
    result = decide(HOT, labels(label()), features=None)

    assert result.tier is AttributionTier.CONFIRMED
    assert result.entity_name == "Binance"
    assert result.method is AttributionMethod.DATASET_MATCH
    # A CONFIRMED claim with no confidence number is the point: it is not a probability.
    assert result.confidence is None
    evidence = result.evidence[0]
    assert evidence["source"] == "Curated exchange wallets"
    assert evidence["source_url"] == "https://example.test/dataset"
    assert evidence["dataset_date"] == "2026-07-01"


def test_a_stale_dataset_stays_confirmed_but_says_when_it_was_current() -> None:
    """The dataset really does say so; the investigator weighs its age."""
    result = decide(HOT, labels(label()), features=None)

    assert result.tier is AttributionTier.CONFIRMED
    assert any("Datasets age" in caveat for caveat in result.caveats)


def test_conflicting_labels_are_both_surfaced_and_neither_is_confirmed() -> None:
    """FR-75. Picking a winner would hide the disagreement that matters."""
    result = decide(
        HOT,
        labels(label(entity="MaskEX", source="Source A"), label(entity="UEEx", source="Source B")),
        features=None,
    )

    assert result.tier is AttributionTier.PROBABLE
    assert result.entity_name is None
    assert result.entity_type is EntityType.EXCHANGE
    assert len(result.evidence) == 2
    assert "MaskEX and UEEx" in result.caveats[0]


def test_agreeing_sources_lead_with_the_more_reliable_one() -> None:
    result = decide(
        HOT,
        labels(
            label(source="Community list", reliability=LabelReliability.LOW),
            label(source="OFAC SDN", reliability=LabelReliability.HIGH),
        ),
        features=None,
    )

    assert result.tier is AttributionTier.CONFIRMED
    assert result.evidence[0]["source"] == "OFAC SDN"
    # Both are still recorded — the investigator sees everything we hold.
    assert len(result.evidence) == 2


# --- Step 3: not enough behaviour to judge -----------------------------------------


def test_insufficient_activity_is_unattributed_with_a_reason() -> None:
    features = extract(OTHER, [tx(SENDERS[0], OTHER, 1_000, minutes=0)])

    result = decide(OTHER, None, features)

    assert result.tier is AttributionTier.UNATTRIBUTED
    assert result.reason == Reason.INSUFFICIENT_ACTIVITY
    assert result.entity_id is None
    assert result.confidence is None
    assert any("KYC records" in str(e["detail"]) for e in result.evidence)


def test_no_retrieved_data_is_not_the_same_as_no_activity() -> None:
    result = decide(OTHER, None, features=None)

    assert result.tier is AttributionTier.UNATTRIBUTED
    assert result.reason == Reason.NO_DATA


def test_a_contract_is_not_run_through_the_deposit_heuristic() -> None:
    """A contract has no customer depositing into it, so the funnel shape means nothing."""
    result = decide(OTHER, None, deposit_features(), is_contract=True)

    assert result.tier is AttributionTier.UNATTRIBUTED
    assert result.reason == Reason.UNIDENTIFIED_CONTRACT


# --- Step 4: the deposit-funnel heuristic and its chained inference ------------------


def test_the_deposit_shape_scores_above_the_threshold() -> None:
    score, fired = funnel_score(deposit_features())

    assert score == Fraction(1)
    assert all(fired.values())


def test_a_confirmed_destination_names_the_exchange() -> None:
    result = decide(
        DEPOSIT, None, deposit_features(), destination=decide(HOT, labels(label()), None)
    )

    assert result.tier is AttributionTier.PROBABLE
    assert result.entity_name == "Binance"
    assert result.entity_type is EntityType.EXCHANGE
    assert result.method is AttributionMethod.DEPOSIT_HEURISTIC
    assert result.confidence == Fraction(95, 100)
    assert any(e["type"] == "CHAINED_INFERENCE" for e in result.evidence)


def test_confidence_propagates_down_through_a_probable_destination() -> None:
    """The conclusion is never more certain than the premise it rests on."""
    probable_destination = AttributionResult(
        tier=AttributionTier.PROBABLE,
        entity_type=EntityType.EXCHANGE,
        method=AttributionMethod.DEPOSIT_HEURISTIC,
        entity_name="Binance",
        confidence=Fraction(1, 2),
        evidence=[{"type": "SIGNAL", "detail": "..."}],
    )
    result = decide(DEPOSIT, None, deposit_features(), destination=probable_destination)

    score, _ = funnel_score(deposit_features())
    assert result.confidence == score * Fraction(1, 2)
    assert result.confidence < score
    assert any("product of two inferences" in caveat for caveat in result.caveats)


def test_an_unattributed_destination_still_produces_a_useful_finding() -> None:
    """ "A deposit address for a service we cannot name" is a real finding, not a failure."""
    unattributed = decide(HOT, None, None)
    result = decide(DEPOSIT, None, deposit_features(), destination=unattributed)

    assert result.tier is AttributionTier.PROBABLE
    assert result.entity_name is None
    assert result.entity_id is None
    assert "unidentified service" in result.caveats[0]


def test_a_deposit_finding_always_discloses_its_lookalikes() -> None:
    """The heuristic does not pretend to be clean (section 4)."""
    result = decide(
        DEPOSIT, None, deposit_features(), destination=decide(HOT, labels(label()), None)
    )

    assert any("payment processor" in caveat for caveat in result.caveats)
    assert any("custodial wallet service" in caveat for caveat in result.caveats)


def test_confidence_is_never_one() -> None:
    """A UI showing 100% confidence on a heuristic is lying."""
    result = decide(
        DEPOSIT, None, deposit_features(), destination=decide(HOT, labels(label()), None)
    )

    assert result.confidence is not None
    assert result.confidence <= CONFIDENCE_CAP < Fraction(1)


def test_weak_but_service_like_behaviour_names_no_entity() -> None:
    """Between 0.4 and 0.7: something is going on, but not enough to name it."""
    transfers = [
        tx(SENDERS[0], OTHER, 1_000, minutes=0),
        tx(SENDERS[1], OTHER, 1_000, minutes=10),
        tx(SENDERS[2], OTHER, 1_000, minutes=20),
        tx(OTHER, HOT, 2_000, minutes=30),
        tx(OTHER, DEPOSIT, 500, minutes=40),
    ]
    features = extract(OTHER, transfers)
    score, _ = funnel_score(features)
    assert score < DEPOSIT_THRESHOLD

    result = decide(OTHER, None, features)

    assert result.tier is AttributionTier.PROBABLE
    assert result.entity_name is None
    assert result.entity_type is EntityType.UNKNOWN


def test_an_ordinary_wallet_is_unattributed_not_cleared() -> None:
    """ "Not an exchange" is a claim we cannot make; "no evidence" is what we say."""
    transfers = [
        tx(SENDERS[0], OTHER, 5_000_000, minutes=0),
        tx(SENDERS[1], OTHER, 5_000_000, minutes=1_440),
        tx(SENDERS[2], OTHER, 5_000_000, minutes=2_880),
        tx(OTHER, SENDERS[3], 1_000_000, minutes=10_000),
        tx(OTHER, DEPOSIT, 1_000_000, minutes=20_000),
        tx(OTHER, HOT, 1_000_000, minutes=30_000),
    ]
    result = decide(OTHER, None, extract(OTHER, transfers))

    assert result.tier is AttributionTier.UNATTRIBUTED
    assert result.reason == Reason.NO_SERVICE_BEHAVIOUR


# --- The service boundary a trace stops at ------------------------------------------


def test_only_a_confirmed_service_stops_a_trace() -> None:
    """Stopping on a guess would truncate the answer silently."""
    confirmed = decide(HOT, labels(label()), None)
    probable = decide(DEPOSIT, None, deposit_features(), destination=confirmed)

    assert confirmed.is_service is True
    assert probable.is_service is False
    assert decide(OTHER, None, None).is_service is False


def test_a_confirmed_non_service_does_not_stop_a_trace() -> None:
    """A sanctioned personal wallet is a finding, not an exchange boundary."""
    sanctioned = decide(
        OTHER,
        labels(
            label(
                address=OTHER, entity="OFAC SDN designated party", entity_type=EntityType.SANCTIONED
            )
        ),
        None,
    )

    assert sanctioned.tier is AttributionTier.CONFIRMED
    assert sanctioned.is_service is False


# --- Storage forms -------------------------------------------------------------------


def test_confidence_converts_to_the_stored_decimal_exactly() -> None:
    result = decide(
        DEPOSIT, None, deposit_features(), destination=decide(HOT, labels(label()), None)
    )

    assert result.confidence_decimal is not None
    assert float(result.confidence_decimal) == 0.95
    assert decide(HOT, labels(label()), None).confidence_decimal is None


def test_every_tiered_claim_carries_evidence() -> None:
    """The database CHECK constraint requires it; nothing here may produce an empty list."""
    cases = [
        decide(HOT, labels(label()), None),
        decide(DEPOSIT, None, deposit_features(), destination=decide(HOT, labels(label()), None)),
        decide(DEPOSIT, None, deposit_features()),
        decide(OTHER, None, None),
        decide(OTHER, None, extract(OTHER, [tx(SENDERS[0], OTHER, 1, minutes=0)])),
    ]
    for result in cases:
        assert result.evidence, result
        if result.tier is AttributionTier.UNATTRIBUTED:
            assert result.reason is not None
