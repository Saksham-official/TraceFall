"""The decision procedure — VASP_IDENTIFICATION.md section 7.

Pure: labels and features in, a tiered conclusion out. No database, no network, so the
product's central claim is testable without either.

Three rules govern everything here:

**The tiers are never collapsed.** `CONFIRMED` means a named, dated source says so.
`PROBABLE` means we inferred it from behaviour, and the evidence is shown. `UNATTRIBUTED`
means we do not know — and reaching it often is the system working correctly, not failing.

**Confidence is bounded by the weakest link.** "X sweeps to Y, and Y is Binance" is only
as good as our knowledge of Y. A chain of guesses is never laundered into a confident
answer.

**Confidence is capped below 1.0.** Behavioural inference does not produce certainty, and
a UI showing 100% on a heuristic is lying.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from fractions import Fraction

from app.db.models.enums import AttributionMethod, AttributionTier, EntityType
from app.intel.features import AddressFeatures
from app.labels.matcher import AddressLabels

# Bumped whenever a weight, threshold or rule below changes, and stored on every row so
# an old assessment stays readable next to a new one.
ENGINE_VERSION = "1.0.0"

# Deposit-funnel signals and their weights. Each is a stated threshold that either holds
# or does not, so a finding can be explained in one sentence — a graded score reads
# better on a chart and worse in a witness box.
#
# ponytail: thresholds are the reasoned defaults from OQ-09, not calibrated ones. They
# move to config/ alongside the risk weights once there is a labelled set to calibrate
# against; OQ-09 is explicit that this number decides whether a legal request goes to the
# right institution.
SWEEP_CONSISTENCY_MIN = Fraction(95, 100)
BALANCE_RETENTION_MAX = Fraction(2, 100)
DWELL_SECONDS_MAX = 3600
COUNTERPARTY_IN_MIN = 3
COUNTERPARTY_OUT_MAX = 2

WEIGHTS = {
    "sweep_consistency": Fraction(30, 100),
    "balance_retention": Fraction(20, 100),
    "dwell_time": Fraction(15, 100),
    "counterparty_diversity_in": Fraction(15, 100),
    "counterparty_diversity_out": Fraction(10, 100),
    "no_independent_activity": Fraction(10, 100),
}

DEPOSIT_THRESHOLD = Fraction(70, 100)
SERVICE_LIKE_THRESHOLD = Fraction(40, 100)
CONFIDENCE_CAP = Fraction(95, 100)
# A hub is a service, but which service is unidentified — a genuinely weak claim.
HUB_CONFIDENCE = Fraction(40, 100)
# Sources naming different operators: the type is agreed, the operator is not.
CONFLICT_CONFIDENCE = Fraction(50, 100)

# Entity types whose addresses a trace must not be followed past: everything downstream
# belongs to other customers, not to the suspect.
SERVICE_TYPES = frozenset(
    {EntityType.EXCHANGE, EntityType.MIXER, EntityType.BRIDGE, EntityType.MERCHANT}
)


class Reason:
    """Why an address ended `UNATTRIBUTED`. Stated, never left blank."""

    INSUFFICIENT_ACTIVITY = "INSUFFICIENT_ACTIVITY"
    UNIDENTIFIED_CONTRACT = "UNIDENTIFIED_CONTRACT"
    NO_SERVICE_BEHAVIOUR = "NO_SERVICE_BEHAVIOUR"
    NO_DATA = "NO_DATA"


@dataclass(frozen=True)
class AttributionResult:
    tier: AttributionTier
    entity_type: EntityType
    method: AttributionMethod
    entity_id: int | None = None
    entity_name: str | None = None
    confidence: Fraction | None = None
    evidence: list[dict[str, object]] = field(default_factory=list)
    reason: str | None = None
    # What else this evidence is consistent with. Shown to the investigator verbatim;
    # a heuristic that hides its look-alikes is a heuristic that will be trusted too far.
    caveats: list[str] = field(default_factory=list)

    @property
    def confidence_decimal(self) -> Decimal | None:
        """Storage form. Twelve places matches the column, and rounds nothing that matters."""
        if self.confidence is None:
            return None
        return Decimal(self.confidence.numerator) / Decimal(self.confidence.denominator)

    @property
    def is_service(self) -> bool:
        """Whether a trace should stop here (WALLET_TRACING.md service boundary).

        Only a confirmed service stops a trace. Stopping on a guess would silently
        truncate the answer, and a truncated trace is the failure this product exists to
        avoid.
        """
        return self.tier is AttributionTier.CONFIRMED and self.entity_type in SERVICE_TYPES


DEPOSIT_LOOKALIKES = [
    "a payment processor with a similar sweep pattern",
    "a custodial wallet service, which is structurally identical",
    "an automated sweeper operated by a legitimate business",
]


def decide(
    address: str,
    labels: AddressLabels | None,
    features: AddressFeatures | None,
    destination: "AttributionResult | None" = None,
    is_contract: bool | None = None,
) -> AttributionResult:
    """Apply the section 7 procedure to one address.

    `destination` is the already-decided attribution of the address this one sweeps to —
    the second half of the chained inference, and the thing that bounds the confidence.
    """
    if confirmed := _dataset_match(labels):
        return confirmed

    # A contract does not have a customer depositing into it, so the funnel heuristic
    # does not apply. Classifying a contract by its type needs bytecode and ABI knowledge
    # the system does not gather yet, so the honest answer is that it is unidentified.
    if is_contract:
        return AttributionResult(
            tier=AttributionTier.UNATTRIBUTED,
            entity_type=EntityType.UNKNOWN,
            method=AttributionMethod.DATASET_MATCH,
            reason=Reason.UNIDENTIFIED_CONTRACT,
            evidence=[
                {
                    "type": "OBSERVATION",
                    "detail": (
                        f"{address} is a smart contract and appears in no known-address dataset"
                    ),
                }
            ],
        )

    if features is None:
        return _unattributed(address, Reason.NO_DATA, "no transfers have been retrieved for it")
    if not features.has_sufficient_activity:
        return _unattributed(
            address,
            Reason.INSUFFICIENT_ACTIVITY,
            f"it has {features.tx_count_in} inbound and {features.tx_count_out} outbound "
            f"transfers, below the minimum needed to describe behaviour",
            features=features,
        )

    score, fired = funnel_score(features)
    if score >= DEPOSIT_THRESHOLD:
        return _deposit_address(address, features, score, fired, destination)
    if score >= SERVICE_LIKE_THRESHOLD:
        return AttributionResult(
            tier=AttributionTier.PROBABLE,
            entity_type=EntityType.UNKNOWN,
            method=AttributionMethod.DEPOSIT_HEURISTIC,
            confidence=min(score, CONFIDENCE_CAP),
            evidence=_signal_evidence(address, features, fired),
            caveats=["The behaviour is service-like but too weak to name a service type."],
        )
    if features.is_high_volume_bidirectional:
        return AttributionResult(
            tier=AttributionTier.PROBABLE,
            entity_type=EntityType.UNKNOWN,
            method=AttributionMethod.DEPOSIT_HEURISTIC,
            confidence=HUB_CONFIDENCE,
            evidence=[
                {
                    "type": "OBSERVATION",
                    "detail": (
                        f"{address} moves value in both directions at high volume: "
                        f"{features.tx_count_in} in from {features.counterparty_diversity_in} "
                        f"senders, {features.tx_count_out} out to "
                        f"{features.counterparty_diversity_out} recipients"
                    ),
                }
            ],
            caveats=["A high-volume hub is some kind of service; which one is not identified."],
        )
    return _unattributed(
        address,
        Reason.NO_SERVICE_BEHAVIOUR,
        "it does not appear in any known-address dataset and does not exhibit "
        "service-like behaviour",
        features=features,
    )


def funnel_score(features: AddressFeatures) -> tuple[Fraction, dict[str, bool]]:
    """Score the deposit-address shape. Returns the score and which signals fired."""
    fired = {
        "sweep_consistency": features.sweep_consistency is not None
        and features.sweep_consistency >= SWEEP_CONSISTENCY_MIN,
        "balance_retention": features.balance_retention is not None
        and features.balance_retention <= BALANCE_RETENTION_MAX,
        "dwell_time": features.median_dwell_seconds is not None
        and features.median_dwell_seconds <= DWELL_SECONDS_MAX,
        "counterparty_diversity_in": features.counterparty_diversity_in >= COUNTERPARTY_IN_MIN,
        "counterparty_diversity_out": 0
        < features.counterparty_diversity_out
        <= COUNTERPARTY_OUT_MAX,
        "no_independent_activity": not features.initiates_transfers,
    }
    score = sum((WEIGHTS[name] for name, held in fired.items() if held), Fraction(0))
    return score, fired


def _dataset_match(labels: AddressLabels | None) -> AttributionResult | None:
    """Step 1. A named, dated source is the only thing that produces `CONFIRMED`."""
    if labels is None or not labels.matches:
        return None

    if labels.conflicted:
        # Two sources naming different operators. Both are reported and neither is
        # confirmed — picking one would be the exact failure the tiers exist to prevent.
        types = {m.entity_type for m in labels.matches}
        named = " and ".join(sorted({m.entity_name or "unnamed" for m in labels.matches}))
        return AttributionResult(
            tier=AttributionTier.PROBABLE,
            entity_type=types.pop() if len(types) == 1 else EntityType.UNKNOWN,
            method=AttributionMethod.DATASET_MATCH,
            confidence=CONFLICT_CONFIDENCE,
            evidence=[m.as_evidence() for m in labels.matches],
            caveats=[
                f"Sources disagree on the operator of this address: {named}. "
                f"It is not confirmed as either."
            ],
        )

    best = labels.best
    assert best is not None
    # The most reliable, most recent source leads. Every other source we hold follows —
    # the investigator sees all of it, in the order that helps them.
    corroborating = [m for m in labels.matches if m is not best]
    return AttributionResult(
        tier=AttributionTier.CONFIRMED,
        entity_id=best.entity_id,
        entity_name=best.entity_name,
        entity_type=best.entity_type,
        method=AttributionMethod.DATASET_MATCH,
        evidence=[best.as_evidence()] + [m.as_evidence() for m in corroborating],
        caveats=(
            [
                "Datasets age. This label is as of the dataset date shown; the address "
                "may since have been retired."
            ]
            if best.dataset_date
            else []
        ),
    )


def _deposit_address(
    address: str,
    features: AddressFeatures,
    score: Fraction,
    fired: dict[str, bool],
    destination: AttributionResult | None,
) -> AttributionResult:
    """Step 4 — the chained inference, and the place confidence is bounded.

    The address behaves like a deposit address. Naming the exchange behind it requires a
    second claim about where it sweeps to, and that claim's confidence multiplies in.
    """
    evidence = _signal_evidence(address, features, fired)
    caveats = [f"Also consistent with {lookalike}." for lookalike in DEPOSIT_LOOKALIKES]

    if destination is None or destination.tier is AttributionTier.UNATTRIBUTED:
        return AttributionResult(
            tier=AttributionTier.PROBABLE,
            entity_type=EntityType.UNKNOWN,
            method=AttributionMethod.DEPOSIT_HEURISTIC,
            confidence=min(score, CONFIDENCE_CAP),
            evidence=evidence,
            caveats=[
                "This is a deposit address for an unidentified service. The service it "
                "sweeps to could not be attributed.",
                *caveats,
            ],
        )

    if destination.tier is AttributionTier.CONFIRMED:
        confidence = score
    else:
        # Probable destination: the conclusion cannot be more certain than the premise.
        confidence = score * (destination.confidence or Fraction(0))

    evidence.append(
        {
            "type": "CHAINED_INFERENCE",
            "detail": (
                f"{features.dominant_out_destination} is attributed to "
                f"{destination.entity_name or 'an unidentified service'} "
                f"({destination.tier})"
            ),
            "destination": features.dominant_out_destination,
            "destination_tier": str(destination.tier),
        }
    )
    if destination.tier is AttributionTier.PROBABLE:
        caveats.insert(
            0,
            "The sweep destination is itself only a probable attribution, so this "
            "confidence is the product of two inferences.",
        )
    return AttributionResult(
        tier=AttributionTier.PROBABLE,
        entity_id=destination.entity_id,
        entity_name=destination.entity_name,
        entity_type=destination.entity_type,
        method=AttributionMethod.DEPOSIT_HEURISTIC,
        confidence=min(confidence, CONFIDENCE_CAP),
        evidence=evidence,
        caveats=caveats,
    )


def _signal_evidence(
    address: str, features: AddressFeatures, fired: dict[str, bool]
) -> list[dict[str, object]]:
    """One evidence line per signal that fired, in plain language.

    Signals that did not fire are omitted rather than listed as zero — but a signal that
    could not be measured is recorded, so "not evaluated" stays distinct from "no".
    """
    descriptions: dict[str, Callable[[], str]] = {
        "sweep_consistency": lambda: (
            f"{_percent(features.sweep_consistency)} of outbound value went to a single "
            f"destination, {features.dominant_out_destination}"
        ),
        "balance_retention": lambda: (
            f"retains {_percent(features.balance_retention)} of the value it received"
        ),
        "dwell_time": lambda: (
            f"forwards receipts after a median of {features.median_dwell_seconds} seconds"
        ),
        "counterparty_diversity_in": lambda: (
            f"received from {features.counterparty_diversity_in} distinct addresses"
        ),
        "counterparty_diversity_out": lambda: (
            f"sends to only {features.counterparty_diversity_out} distinct destination(s)"
        ),
        "no_independent_activity": lambda: "never sends without first having received",
    }
    evidence: list[dict[str, object]] = [
        {"type": "SIGNAL", "signal": name, "detail": f"{address} {descriptions[name]()}"}
        for name, held in fired.items()
        if held
    ]
    if features.contract_interaction_rate is None:
        evidence.append(
            {
                "type": "NOT_EVALUATED",
                "signal": "contract_interaction_rate",
                "detail": "Contract interaction was not evaluated; it is not derivable "
                "from transfer data alone.",
            }
        )
    return evidence


def _unattributed(
    address: str, reason: str, detail: str, features: AddressFeatures | None = None
) -> AttributionResult:
    evidence: list[dict[str, object]] = [
        {"type": "OBSERVATION", "detail": f"{address}: {detail}"},
        {
            "type": "WHAT_WOULD_BE_NEEDED",
            "detail": "Identifying the controller requires KYC records held by a VASP, "
            "or data sources beyond public blockchain analytics.",
        },
    ]
    if features is not None:
        evidence.insert(1, {"type": "FEATURES", "detail": features.as_dict()})
    return AttributionResult(
        tier=AttributionTier.UNATTRIBUTED,
        entity_type=EntityType.UNKNOWN,
        method=AttributionMethod.DEPOSIT_HEURISTIC,
        reason=reason,
        evidence=evidence,
    )


def _percent(value: Fraction | None) -> str:
    return "unknown" if value is None else f"{float(value) * 100:.1f}%"
