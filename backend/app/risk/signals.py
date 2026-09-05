"""Signal evaluators — one pure function each.

Every evaluator takes the same input bundle and its own config block, and returns either
a `Signal` with its points and a plain-language description, or `NotEvaluated` naming the
input it lacked.

**Signals never interact.** No conditional weighting, no multiplicative terms. That is
what keeps the breakdown readable and the arithmetic checkable by hand — an investigator
must be able to add the points up themselves.

**Descriptions carry concrete numbers.** "Suspicious velocity detected" is useless in a
witness box; "distributed to 47 addresses within 6 minutes" is testimony.

**`NotEvaluated` is not zero.** "We did not check" and "we checked and found nothing" are
different facts, and collapsing them would inflate confidence exactly where the data is
weakest.
"""

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.attribution.decision import AttributionResult
from app.db.models.enums import EntityType, PatternType
from app.intel.features import AddressFeatures
from app.patterns.base import Finding
from app.risk.config import SignalConfig


@dataclass(frozen=True, slots=True)
class RiskContact:
    """A risky entity the traced value reached, and how far away it is."""

    address: str
    entity_type: EntityType
    entity_name: str | None
    hops: int
    tx_hashes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SignalInput:
    """Everything the evaluators are allowed to see. Assembled by the engine."""

    address: str
    features: AddressFeatures | None = None
    attribution: AttributionResult | None = None
    patterns: list[Finding] = field(default_factory=list)
    contacts: list[RiskContact] = field(default_factory=list)
    tainted_amount_raw: int = 0
    asset_symbol: str | None = None
    # None means the question was not asked, which is different from a negative answer.
    cross_case_match: bool | None = None
    victim_count: int | None = None

    def pattern(self, pattern_type: PatternType) -> Finding | None:
        return next((f for f in self.patterns if f.pattern_type is pattern_type), None)

    def nearest(self, *entity_types: EntityType) -> RiskContact | None:
        matching = [c for c in self.contacts if c.entity_type in entity_types]
        return min(matching, key=lambda c: c.hops) if matching else None


@dataclass(frozen=True)
class Signal:
    name: str
    weight: float
    points: float
    raw_value: Any
    description: str
    evidence_tx: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "weight": round(self.weight, 2),
            "points": round(self.points, 2),
            "raw_value": self.raw_value,
            "description": self.description,
            "evidence_tx": self.evidence_tx,
        }


@dataclass(frozen=True)
class NotEvaluated:
    name: str
    reason: str

    def as_dict(self) -> dict[str, str]:
        return {"name": self.name, "reason": self.reason}


Outcome = Signal | NotEvaluated
Evaluator = Callable[[SignalInput, SignalConfig], Outcome]
REGISTRY: dict[str, Evaluator] = {}


def evaluator(name: str) -> Callable[[Evaluator], Evaluator]:
    def wrap(fn: Evaluator) -> Evaluator:
        REGISTRY[name] = fn
        return fn

    return wrap


# --- Group A — direct risk contact ---------------------------------------------------
# These rest on CONFIRMED dataset matches: observed fact, not inference. Hop-scaled,
# because an address that sends to a mixer two hops away is implicated by that and one
# sitting three hops downstream of something bad is not.


def _contact_signal(
    name: str,
    data: SignalInput,
    config: SignalConfig,
    entity_types: tuple[EntityType, ...],
    verb: str,
) -> Outcome:
    contact = data.nearest(*entity_types)
    if contact is None:
        return Signal(name, config.weight, 0.0, False, f"No traced value {verb}.")
    decay = config.get("hop_decay", 0.2)
    points = config.weight * max(0.0, (1 - decay) ** contact.hops)
    named = contact.entity_name or "an address on a sanctions or service list"
    where = "directly" if contact.hops == 0 else f"at hop {contact.hops}"
    return Signal(
        name=name,
        weight=config.weight,
        points=points,
        raw_value=contact.hops,
        description=f"Traced value {verb.replace('reached', 'reached')} {named} {where}.",
        evidence_tx=contact.tx_hashes,
    )


@evaluator("sanctioned_contact")
def sanctioned_contact(data: SignalInput, config: SignalConfig) -> Outcome:
    return _contact_signal(
        "sanctioned_contact", data, config, (EntityType.SANCTIONED,), "reached a sanctioned address"
    )


@evaluator("mixer_interaction")
def mixer_interaction(data: SignalInput, config: SignalConfig) -> Outcome:
    return _contact_signal(
        "mixer_interaction", data, config, (EntityType.MIXER,), "reached a known mixer"
    )


@evaluator("darknet_contact")
def darknet_contact(data: SignalInput, config: SignalConfig) -> Outcome:
    # There is no darknet label set in `data/labels/`, and inferring one from behaviour
    # would be a guess wearing the clothes of a dataset match.
    return NotEvaluated("darknet_contact", "No darknet-association label dataset is loaded.")


@evaluator("high_risk_jurisdiction_vasp")
def high_risk_jurisdiction_vasp(data: SignalInput, config: SignalConfig) -> Outcome:
    contact = data.nearest(EntityType.EXCHANGE)
    if contact is None:
        return NotEvaluated("high_risk_jurisdiction_vasp", "No VASP was identified in this trace.")
    # `entities.jurisdiction` exists but no committed dataset populates it, and there is
    # no agreed high-risk list in the repository to compare it against.
    return NotEvaluated(
        "high_risk_jurisdiction_vasp",
        f"Jurisdiction is not recorded for {contact.entity_name or 'the identified VASP'}.",
    )


# --- Group B — laundering behaviour --------------------------------------------------


@evaluator("rapid_transfer")
def rapid_transfer(data: SignalInput, config: SignalConfig) -> Outcome:
    if data.features is None or data.features.median_dwell_seconds is None:
        return NotEvaluated("rapid_transfer", "No receipt-then-send pair was observed.")
    seconds = data.features.median_dwell_seconds
    fraction = _decay(
        seconds,
        config.get("full_points_below_seconds", 60),
        config.get("zero_points_above_seconds", 86_400),
    )
    return Signal(
        name="rapid_transfer",
        weight=config.weight,
        points=config.weight * fraction,
        raw_value=seconds,
        description=(
            f"Funds held for a median of {seconds} seconds before onward transfer."
            if fraction > 0
            else f"Funds held for a median of {seconds} seconds — no urgency in the movement."
        ),
    )


def _degree_signal(name: str, count: int, config: SignalConfig, description: str) -> Signal:
    fraction = _log_scale(count, config.get("threshold", 5), config.get("saturation", 50))
    return Signal(name, config.weight, config.weight * fraction, count, description)


@evaluator("fan_out")
def fan_out(data: SignalInput, config: SignalConfig) -> Outcome:
    if data.features is None:
        return NotEvaluated("fan_out", "No behavioural profile was computed for this address.")
    count = data.features.counterparty_diversity_out
    return _degree_signal(
        "fan_out", count, config, f"Distributed funds to {count} distinct addresses."
    )


@evaluator("fan_in")
def fan_in(data: SignalInput, config: SignalConfig) -> Outcome:
    if data.features is None:
        return NotEvaluated("fan_in", "No behavioural profile was computed for this address.")
    count = data.features.counterparty_diversity_in
    return _degree_signal(
        "fan_in", count, config, f"Received funds from {count} distinct addresses."
    )


def _pattern_signal(
    name: str, pattern_type: PatternType, data: SignalInput, config: SignalConfig, absent: str
) -> Outcome:
    finding = data.pattern(pattern_type)
    if finding is None:
        return Signal(name, config.weight, 0.0, False, absent)
    return Signal(
        name=name,
        weight=config.weight,
        points=config.weight,
        raw_value=finding.metrics,
        description=finding.explanation,
        evidence_tx=finding.trigger_tx_hashes,
    )


@evaluator("peel_chain")
def peel_chain(data: SignalInput, config: SignalConfig) -> Outcome:
    return _pattern_signal(
        "peel_chain", PatternType.PEEL_CHAIN, data, config, "No peel structure was detected."
    )


@evaluator("structuring")
def structuring(data: SignalInput, config: SignalConfig) -> Outcome:
    return _pattern_signal(
        "structuring", PatternType.STRUCTURING, data, config, "No repeated identical amounts."
    )


@evaluator("dormancy_burst")
def dormancy_burst(data: SignalInput, config: SignalConfig) -> Outcome:
    return _pattern_signal(
        "dormancy_burst",
        PatternType.DORMANCY_BURST,
        data,
        config,
        "No long dormancy followed by a burst of activity.",
    )


@evaluator("chain_hopping")
def chain_hopping(data: SignalInput, config: SignalConfig) -> Outcome:
    return _contact_signal(
        "chain_hopping", data, config, (EntityType.BRIDGE,), "reached a cross-chain bridge"
    )


# --- Group C — address characteristics -----------------------------------------------


@evaluator("wallet_age")
def wallet_age(data: SignalInput, config: SignalConfig) -> Outcome:
    if data.features is None or data.features.age_days is None:
        return NotEvaluated("wallet_age", "First-seen time is unavailable for this address.")
    days = data.features.age_days
    fraction = _decay(
        days, config.get("full_points_below_days", 7), config.get("zero_points_above_days", 180)
    )
    return Signal(
        name="wallet_age",
        weight=config.weight,
        points=config.weight * fraction,
        raw_value=days,
        description=f"Address has been active over a span of {days} days.",
    )


@evaluator("pass_through_ratio")
def pass_through_ratio(data: SignalInput, config: SignalConfig) -> Outcome:
    if data.features is None or data.features.balance_retention is None:
        return NotEvaluated("pass_through_ratio", "The address received nothing to retain.")
    retention = float(data.features.balance_retention)
    limit = config.get("max_retention", 0.05)
    fires = retention <= limit and data.features.total_out_raw > 0
    return Signal(
        name="pass_through_ratio",
        weight=config.weight,
        points=config.weight if fires else 0.0,
        raw_value=round(retention, 4),
        description=(
            f"Forwarded effectively everything it received, retaining {retention * 100:.2f}%."
            if fires
            else f"Retains {retention * 100:.2f}% of what it received."
        ),
    )


@evaluator("velocity")
def velocity(data: SignalInput, config: SignalConfig) -> Outcome:
    if data.features is None or not data.features.active_days:
        return NotEvaluated("velocity", "No activity span was measured for this address.")
    total = data.features.tx_count_in + data.features.tx_count_out
    per_day = total / data.features.active_days
    fraction = _log_scale(per_day, config.get("threshold", 1), config.get("saturation", 100))
    return Signal(
        name="velocity",
        weight=config.weight,
        points=config.weight * fraction,
        raw_value=round(per_day, 2),
        description=f"{total} transfers across {data.features.active_days} active day(s).",
    )


@evaluator("single_use_pattern")
def single_use_pattern(data: SignalInput, config: SignalConfig) -> Outcome:
    if data.features is None:
        return NotEvaluated(
            "single_use_pattern", "No behavioural profile was computed for this address."
        )
    fires = data.features.tx_count_in == 1 and data.features.tx_count_out == 1
    return Signal(
        name="single_use_pattern",
        weight=config.weight,
        points=config.weight if fires else 0.0,
        raw_value=[data.features.tx_count_in, data.features.tx_count_out],
        description=(
            "Received once and forwarded once, then never used again."
            if fires
            else f"Used {data.features.tx_count_in} times in and "
            f"{data.features.tx_count_out} times out."
        ),
    )


@evaluator("no_legitimate_activity")
def no_legitimate_activity(data: SignalInput, config: SignalConfig) -> Outcome:
    # The signal is "no contract interaction, no DeFi, no diverse assets". Contract
    # interaction is not derivable from transfer data alone, and scoring on the half we
    # can see would be a different signal wearing this one's name.
    return NotEvaluated(
        "no_legitimate_activity",
        "Contract interaction is not derivable from transfer data alone.",
    )


# --- Group D — case context -----------------------------------------------------------


@evaluator("cross_case_match")
def cross_case_match(data: SignalInput, config: SignalConfig) -> Outcome:
    if data.cross_case_match is None:
        return NotEvaluated("cross_case_match", "Cross-case correlation was not run.")
    return Signal(
        name="cross_case_match",
        weight=config.weight,
        points=config.weight if data.cross_case_match else 0.0,
        raw_value=data.cross_case_match,
        description=(
            "This address already appears in another open case."
            if data.cross_case_match
            else "This address does not appear in any other open case."
        ),
    )


@evaluator("victim_count")
def victim_count(data: SignalInput, config: SignalConfig) -> Outcome:
    if data.victim_count is None:
        # Identifying probable victims needs backward tracing, which is not built.
        return NotEvaluated("victim_count", "Backward tracing was not run for this analysis.")
    fraction = _log_scale(
        data.victim_count, config.get("threshold", 1), config.get("saturation", 20)
    )
    return Signal(
        name="victim_count",
        weight=config.weight,
        points=config.weight * fraction,
        raw_value=data.victim_count,
        description=f"{data.victim_count} distinct probable-victim payers identified.",
    )


@evaluator("value_magnitude")
def value_magnitude(data: SignalInput, config: SignalConfig) -> Outcome:
    amount = data.tainted_amount_raw
    fraction = _log_scale(
        amount, config.get("threshold", 1_000_000), config.get("saturation", 10**12)
    )
    asset = data.asset_symbol or "units"
    return Signal(
        name="value_magnitude",
        weight=config.weight,
        points=config.weight * fraction,
        raw_value=str(amount),
        description=f"{amount} raw {asset} of traced value reached this address.",
    )


# --- Scaling helpers ------------------------------------------------------------------


def _decay(value: float, full_below: float, zero_above: float) -> float:
    """1.0 at or below `full_below`, 0.0 at or above `zero_above`, linear between."""
    if value <= full_below:
        return 1.0
    if value >= zero_above:
        return 0.0
    return 1.0 - (value - full_below) / (zero_above - full_below)


def _log_scale(value: float, threshold: float, saturation: float) -> float:
    """0.0 at or below `threshold`, 1.0 at or above `saturation`, log-scaled between.

    Logarithmic because the difference between 5 and 50 recipients matters far more than
    between 500 and 550, and a linear scale would let one extreme address dominate.
    """
    if value <= threshold or saturation <= threshold:
        return 0.0
    if value >= saturation:
        return 1.0
    return math.log(value / threshold) / math.log(saturation / threshold)
