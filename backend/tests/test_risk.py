"""The risk engine.

The weights here are expert-reasoned, not empirically calibrated, and no test can fix
that. What these tests can check is that the arithmetic is honest: that the score is
deterministic and reproducible, that adding a risk signal never lowers it, that a missing
input lands in `not_evaluated` rather than as a silent zero, that confidence stays out of
the score — and the sanity anchors, of which **an exchange hot wallet must not score
HIGH** is the one that matters most. A risk engine that flags exchanges is broken, and it
is an easy way to be broken.
"""

from datetime import UTC, datetime, timedelta
from fractions import Fraction

import pytest

from app.attribution.decision import AttributionResult
from app.db.models.enums import (
    AttributionMethod,
    AttributionTier,
    EntityType,
    PatternType,
    RiskBand,
    Severity,
)
from app.intel.features import extract
from app.patterns.base import Finding
from app.risk import config as risk_config
from app.risk import signals as sig
from app.risk.engine import DISCLAIMER, Assessment, score
from app.risk.signals import NotEvaluated, RiskContact, Signal, SignalInput
from tests.tracing_fixtures import tx

CONFIG = risk_config.load()
ADDRESS = "TSubject"


def data(**overrides: object) -> SignalInput:
    return SignalInput(address=ADDRESS, **overrides)  # type: ignore[arg-type]


def assess(**overrides: object) -> Assessment:
    return score(data(**overrides), confidence=1.0, config=CONFIG)


def contact(entity_type: EntityType, hops: int = 0, name: str = "Tornado Cash") -> RiskContact:
    return RiskContact(
        address="TRisky", entity_type=entity_type, entity_name=name, hops=hops, tx_hashes=["a91f"]
    )


def finding(pattern_type: PatternType) -> Finding:
    return Finding(
        pattern_type=pattern_type,
        severity=Severity.HIGH,
        subject_address=ADDRESS,
        explanation=f"{pattern_type} was detected.",
        trigger_tx_hashes=["deadbeef"],
        metrics={"n": 3},
        false_positive_note="note",
    )


def mule_features():  # type: ignore[no-untyped-def]
    """A fresh address that receives from many senders and forwards everything at once."""
    transfers = []
    for i in range(12):
        transfers.append(tx(f"IN{i:02d}", ADDRESS, 1_000_000, i))
    transfers.append(tx(ADDRESS, "OUT", 12_000_000, 13))
    return extract(ADDRESS, transfers)


# --- The configuration ----------------------------------------------------------------


def test_the_committed_config_loads_and_validates() -> None:
    assert CONFIG.version
    assert CONFIG.signals
    # Every registered evaluator has a config block, and every block has an evaluator.
    assert set(sig.REGISTRY) == set(CONFIG.signals)


def test_bands_cover_every_score_with_no_gaps() -> None:
    for value in range(0, 101):
        assert CONFIG.band_for(value) in RiskBand.__members__.values()
    assert CONFIG.band_for(0) is RiskBand.LOW
    assert CONFIG.band_for(24) is RiskBand.LOW
    assert CONFIG.band_for(25) is RiskBand.MEDIUM
    assert CONFIG.band_for(49) is RiskBand.MEDIUM
    assert CONFIG.band_for(50) is RiskBand.HIGH
    assert CONFIG.band_for(74) is RiskBand.HIGH
    assert CONFIG.band_for(75) is RiskBand.CRITICAL
    assert CONFIG.band_for(100) is RiskBand.CRITICAL


def test_a_config_with_a_gap_between_bands_is_rejected() -> None:
    """A score that falls in no band would be unscoreable, so this fails on load."""
    with pytest.raises(ValueError, match="gap or overlap"):
        risk_config.RiskConfig.model_validate(
            {
                "version": "broken",
                "bands": {
                    "LOW": [0, 24],
                    "MEDIUM": [26, 49],
                    "HIGH": [50, 74],
                    "CRITICAL": [75, 100],
                },
                "confidence": {
                    "data_completeness": 0.4,
                    "attribution_quality": 0.3,
                    "trace_completeness": 0.3,
                },
                "signals": {},
            }
        )


def test_confidence_weights_must_sum_to_one() -> None:
    with pytest.raises(ValueError, match="sum to 1.0"):
        risk_config.RiskConfig.model_validate(
            {
                "version": "broken",
                "bands": {"LOW": [0, 100]},
                "confidence": {
                    "data_completeness": 0.9,
                    "attribution_quality": 0.9,
                    "trace_completeness": 0.9,
                },
                "signals": {},
            }
        )


def test_exchange_interaction_is_not_a_signal() -> None:
    """Reaching an exchange is the system's own success condition, not a risk."""
    assert "exchange_interaction" not in CONFIG.signals
    assert "exchange_interaction" not in sig.REGISTRY


# --- Aggregation ----------------------------------------------------------------------


def test_the_score_is_deterministic() -> None:
    first = assess(features=mule_features(), contacts=[contact(EntityType.MIXER, hops=1)])
    second = assess(features=mule_features(), contacts=[contact(EntityType.MIXER, hops=1)])

    assert first.score == second.score
    assert [s.as_dict() for s in first.signals] == [s.as_dict() for s in second.signals]


def test_adding_a_risk_signal_never_lowers_the_score() -> None:
    """Monotonicity. Signals never interact, so this must hold for every combination."""
    base = assess(features=mule_features())
    additions: list[dict[str, object]] = [
        {"contacts": [contact(EntityType.SANCTIONED)]},
        {"contacts": [contact(EntityType.MIXER)]},
        {"contacts": [contact(EntityType.BRIDGE)]},
        {"patterns": [finding(PatternType.PEEL_CHAIN)]},
        {"patterns": [finding(PatternType.STRUCTURING)]},
        {"patterns": [finding(PatternType.DORMANCY_BURST)]},
        {"cross_case_match": True},
        {"victim_count": 15},
    ]
    for addition in additions:
        with_signal = assess(features=mule_features(), **addition)
        assert with_signal.score >= base.score, addition


def test_a_closer_risk_contact_scores_at_least_as_high_as_a_distant_one() -> None:
    """Hop decay: an address that sends to a mixer directly is more implicated."""
    scores = [
        assess(features=mule_features(), contacts=[contact(EntityType.MIXER, hops=h)]).score
        for h in range(4)
    ]
    assert scores == sorted(scores, reverse=True)


def test_the_score_is_clamped_to_one_hundred() -> None:
    """Group maxima sum to 120, so the ceiling must actually hold."""
    maxed = assess(
        features=mule_features(),
        contacts=[
            contact(EntityType.SANCTIONED),
            contact(EntityType.MIXER),
            contact(EntityType.BRIDGE),
        ],
        patterns=[
            finding(PatternType.PEEL_CHAIN),
            finding(PatternType.STRUCTURING),
            finding(PatternType.DORMANCY_BURST),
        ],
        cross_case_match=True,
        victim_count=50,
        tainted_amount_raw=10**13,
    )
    assert maxed.score == 100
    assert maxed.band is RiskBand.CRITICAL


def test_a_missing_input_is_not_evaluated_rather_than_zero() -> None:
    """ "We did not check" and "we checked and found nothing" are different facts."""
    bare = assess()

    names = {n.name for n in bare.not_evaluated}
    assert "victim_count" in names, "backward tracing is not built, so this cannot be scored"
    assert "darknet_contact" in names
    assert "cross_case_match" in names
    for skipped in bare.not_evaluated:
        assert skipped.reason.strip()
    # Not evaluated contributes nothing, and is not renormalised away.
    assert bare.score == 0


def test_asking_the_cross_case_question_and_getting_no_is_not_the_same_as_not_asking() -> None:
    unasked = assess(features=mule_features())
    answered_no = assess(features=mule_features(), cross_case_match=False)

    assert "cross_case_match" in {n.name for n in unasked.not_evaluated}
    assert "cross_case_match" in {s.name for s in answered_no.signals}
    assert answered_no.score == unasked.score


def test_confidence_is_never_folded_into_the_score() -> None:
    """A score of 84 at 0.4 and 34 at 1.0 must not collapse to the same number."""
    high = score(data(features=mule_features()), confidence=0.4, config=CONFIG)
    same = score(data(features=mule_features()), confidence=1.0, config=CONFIG)

    assert high.score == same.score
    assert high.confidence != same.confidence


def test_every_assessment_carries_its_breakdown_and_the_disclaimer() -> None:
    result = assess(features=mule_features(), contacts=[contact(EntityType.MIXER)])

    assert result.signals
    assert result.as_dict()["disclaimer"] == DISCLAIMER
    assert result.config_version == CONFIG.version
    # Every non-zero score has at least one signal with a populated description.
    scoring = [s for s in result.signals if s.points > 0]
    assert scoring and all(s.description.strip() for s in scoring)
    # Highest contribution first: the breakdown opens with the reason.
    assert result.signals[0].points == max(s.points for s in result.signals)


def test_every_signal_states_its_raw_value_so_the_arithmetic_can_be_checked() -> None:
    result = assess(features=mule_features(), contacts=[contact(EntityType.MIXER, hops=2)])

    for signal in result.signals:
        assert signal.raw_value is not None
        assert signal.weight >= signal.points >= 0


# --- The sanity anchors ---------------------------------------------------------------


def test_a_mixer_adjacent_address_scores_critical() -> None:
    result = assess(
        features=mule_features(),
        contacts=[contact(EntityType.SANCTIONED, hops=0), contact(EntityType.MIXER, hops=1)],
        patterns=[finding(PatternType.PEEL_CHAIN)],
        cross_case_match=True,
        tainted_amount_raw=40_000_000_000,
    )

    assert result.band is RiskBand.CRITICAL
    assert any(s.name == "mixer_interaction" and s.points > 0 for s in result.signals)


def test_a_long_lived_ordinary_wallet_scores_low() -> None:
    """Diverse activity over years, funds held, no risk contact."""
    base = datetime(2023, 1, 1, tzinfo=UTC)
    transfers = []
    for i in range(24):
        when = int((base + timedelta(days=30 * i) - base).total_seconds() // 60)
        transfers.append(tx(f"FRIEND{i % 5}", ADDRESS, 5_000_000, when))
        if i % 3 == 0:
            transfers.append(tx(ADDRESS, f"SHOP{i % 4}", 1_000_000, when + 4_320))

    result = assess(features=extract(ADDRESS, transfers))

    assert result.band is RiskBand.LOW, result.as_dict()


def test_an_exchange_hot_wallet_does_not_score_high_for_being_busy() -> None:
    """The regression that matters: a risk engine that flags exchanges is broken.

    A hot wallet has every behavioural marker the heuristics look for — enormous fan-in,
    enormous fan-out, fast turnaround, near-zero retention. What it does not have is risk
    contact, and reaching an exchange is deliberately not a signal at all.
    """
    transfers = []
    for i in range(200):
        transfers.append(tx(f"CUSTOMER{i:03d}", ADDRESS, 1_000_000, i))
        transfers.append(tx(ADDRESS, f"WITHDRAWAL{i:03d}", 1_000_000, i + 1))

    result = assess(
        features=extract(ADDRESS, transfers),
        attribution=AttributionResult(
            tier=AttributionTier.CONFIRMED,
            entity_type=EntityType.EXCHANGE,
            method=AttributionMethod.DATASET_MATCH,
            entity_name="Binance",
            evidence=[{"type": "DATASET_MATCH"}],
        ),
        contacts=[contact(EntityType.EXCHANGE, hops=0, name="Binance")],
        cross_case_match=False,
    )

    assert result.band is not RiskBand.HIGH, result.as_dict()
    assert result.band is not RiskBand.CRITICAL, result.as_dict()
    assert "exchange_interaction" not in {s.name for s in result.signals}


# --- Individual evaluators ------------------------------------------------------------


def test_rapid_transfer_scales_on_dwell_time() -> None:
    config = CONFIG.signals["rapid_transfer"]
    quick = sig.rapid_transfer(data(features=mule_features()), config)
    assert isinstance(quick, Signal)
    assert quick.points > 0
    assert str(quick.raw_value) in quick.description, "the number an investigator checks"


def test_rapid_transfer_is_not_evaluated_without_a_receipt_then_send_pair() -> None:
    lonely = extract(ADDRESS, [tx("IN", ADDRESS, 1_000, 0)])
    outcome = sig.rapid_transfer(data(features=lonely), CONFIG.signals["rapid_transfer"])

    assert isinstance(outcome, NotEvaluated)
    assert outcome.reason


def test_pass_through_ratio_fires_on_a_conduit_and_not_on_a_holder() -> None:
    config = CONFIG.signals["pass_through_ratio"]
    conduit = sig.pass_through_ratio(data(features=mule_features()), config)
    holder = extract(ADDRESS, [tx("IN", ADDRESS, 1_000_000, 0), tx(ADDRESS, "OUT", 100_000, 10)])
    kept = sig.pass_through_ratio(data(features=holder), config)

    assert isinstance(conduit, Signal) and conduit.points == config.weight
    assert isinstance(kept, Signal) and kept.points == 0


def test_a_contact_signal_cites_the_transactions_behind_it() -> None:
    outcome = sig.mixer_interaction(
        data(contacts=[contact(EntityType.MIXER, hops=1)]), CONFIG.signals["mixer_interaction"]
    )

    assert isinstance(outcome, Signal)
    assert outcome.evidence_tx == ["a91f"]
    assert "Tornado Cash" in outcome.description
    assert "hop 1" in outcome.description


def test_the_stored_confidence_stays_inside_its_constraint() -> None:
    """The column is CHECK (confidence > 0 AND confidence <= 1)."""
    for value in (0.0, 0.0001, 0.5, 1.0):
        stored = Assessment(
            address=ADDRESS,
            score=0,
            band=RiskBand.LOW,
            confidence=value,
            signals=[],
            not_evaluated=[],
            config_version="v",
        ).confidence_decimal
        assert Fraction(0) < Fraction(stored) <= Fraction(1)


def test_a_confirmed_service_says_why_its_behaviour_was_not_scored() -> None:
    """The exemption is stated on every affected signal, not applied silently."""
    exchange = AttributionResult(
        tier=AttributionTier.CONFIRMED,
        entity_type=EntityType.EXCHANGE,
        method=AttributionMethod.DATASET_MATCH,
        entity_name="Binance",
        evidence=[{"type": "DATASET_MATCH"}],
    )
    result = assess(features=mule_features(), attribution=exchange)

    skipped = {n.name: n.reason for n in result.not_evaluated}
    for behavioural in ("rapid_transfer", "fan_out", "fan_in", "pass_through_ratio", "velocity"):
        assert behavioural in skipped, behavioural
        assert "describes the service" in skipped[behavioural]


def test_group_a_still_applies_to_a_confirmed_service() -> None:
    """A service that itself touches a sanctioned address is a real finding."""
    exchange = AttributionResult(
        tier=AttributionTier.CONFIRMED,
        entity_type=EntityType.EXCHANGE,
        method=AttributionMethod.DATASET_MATCH,
        entity_name="Binance",
        evidence=[{"type": "DATASET_MATCH"}],
    )
    clean = assess(features=mule_features(), attribution=exchange)
    tainted = assess(
        features=mule_features(),
        attribution=exchange,
        contacts=[contact(EntityType.SANCTIONED, hops=0)],
    )

    assert tainted.score > clean.score
    assert any(s.name == "sanctioned_contact" and s.points > 0 for s in tainted.signals)


def test_a_probable_exchange_is_still_scored_on_behaviour() -> None:
    """The exemption rests on a CONFIRMED dataset match, never on an inference."""
    probable = AttributionResult(
        tier=AttributionTier.PROBABLE,
        entity_type=EntityType.EXCHANGE,
        method=AttributionMethod.DEPOSIT_HEURISTIC,
        entity_name="Binance",
        confidence=Fraction(9, 10),
        evidence=[{"type": "SIGNAL"}],
    )
    result = assess(features=mule_features(), attribution=probable)

    assert "rapid_transfer" in {s.name for s in result.signals}
    assert result.score > 0


def test_a_confirmed_mixer_is_not_exempt() -> None:
    """Being a mixer is not a service whose behaviour excuses itself."""
    mixer = AttributionResult(
        tier=AttributionTier.CONFIRMED,
        entity_type=EntityType.MIXER,
        method=AttributionMethod.DATASET_MATCH,
        entity_name="Tornado Cash",
        evidence=[{"type": "DATASET_MATCH"}],
    )
    result = assess(features=mule_features(), attribution=mixer)

    assert "rapid_transfer" in {s.name for s in result.signals}
