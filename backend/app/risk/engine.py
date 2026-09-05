"""Scoring, banding, and confidence.

```
raw   = Σ points over all evaluated signals
score = min(100, round(raw))
```

Deliberately simple. Group maxima sum to 120 against a ceiling of 100, so reaching the
top needs strong signals across several groups rather than one loud one.

**No normalisation for missing signals.** A signal that could not be evaluated
contributes nothing and appears in `not_evaluated`; confidence drops instead.
Renormalising would inflate scores for addresses with incomplete data, which is exactly
backwards.

**Confidence is returned separately and never multiplied in.** A score of 84 at 0.4
confidence and a score of 34 at 1.0 confidence would collapse to the same number, and
they mean opposite things: "probably very bad, but we are working from partial data"
against "we looked thoroughly and it is fine".
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from app.attribution.decision import AttributionResult
from app.db.models.enums import AttributionTier, EntityType, RiskBand, TerminationReason
from app.graph.builder import TraceGraph
from app.intel.features import AddressFeatures
from app.patterns.base import Finding
from app.risk import signals as signal_module
from app.risk.config import ENGINE_VERSION, RiskConfig, active
from app.risk.signals import NotEvaluated, RiskContact, Signal, SignalInput
from app.tracing.models import TraceResult

DISCLAIMER = (
    "Investigative prioritisation score. Not a probability of fraud and not evidence of "
    "criminal conduct. Expand to see every contributing signal."
)

# Entity types whose presence downstream is a risk contact. EXCHANGE is deliberately
# absent: reaching an exchange is the system's own success condition, and scoring it as
# risk would mark every successful trace as suspicious.
CONTACT_TYPES = frozenset(
    {EntityType.SANCTIONED, EntityType.MIXER, EntityType.BRIDGE, EntityType.GAMBLING}
)

# An address confirmed as one of these *is* a service: enormous fan-in and fan-out, fast
# turnaround and near-zero retention are how it operates, not evidence against it. Its
# behavioural signals are reported as not-evaluated rather than scored — a risk engine
# that flags exchanges is broken, and this is the easy way to be broken.
#
# Not a conditional weight: signals still never interact. This is a scoping rule about
# whose behaviour is being judged, and it is stated on every affected signal.
BEHAVIOUR_IS_THE_SERVICE = frozenset({EntityType.EXCHANGE, EntityType.MERCHANT})
BEHAVIOURAL_GROUPS = frozenset({"B", "C"})

# A trace that stopped because it ran out of budget saw less than one that stopped
# because the money did.
INCOMPLETE_TERMINATIONS = frozenset(
    {
        TerminationReason.MAX_DEPTH,
        TerminationReason.EDGE_BUDGET,
        TerminationReason.DATA_UNAVAILABLE,
        TerminationReason.TIME_WINDOW,
    }
)


@dataclass(frozen=True)
class Assessment:
    address: str
    score: int
    band: RiskBand
    confidence: float
    signals: list[Signal]
    not_evaluated: list[NotEvaluated]
    config_version: str
    engine_version: str = ENGINE_VERSION

    def as_dict(self) -> dict[str, Any]:
        return {
            "address": self.address,
            "score": self.score,
            "band": str(self.band),
            "confidence": round(self.confidence, 4),
            "config_version": self.config_version,
            "engine_version": self.engine_version,
            "signals": [s.as_dict() for s in self.signals],
            "not_evaluated": [n.as_dict() for n in self.not_evaluated],
            "disclaimer": DISCLAIMER,
        }

    @property
    def confidence_decimal(self) -> Decimal:
        # The column is CHECK (confidence > 0 AND confidence <= 1); a floor keeps an
        # assessment storable when every input was missing.
        return Decimal(str(max(round(self.confidence, 4), 0.0001)))


@dataclass
class Inputs:
    """Everything scoring needs, gathered once per run rather than per address."""

    trace: TraceResult
    graph: TraceGraph
    features: dict[str, AddressFeatures] = field(default_factory=dict)
    attributions: dict[str, AttributionResult] = field(default_factory=dict)
    findings: list[Finding] = field(default_factory=list)
    cross_case: dict[str, bool] = field(default_factory=dict)
    data_complete: bool = True
    asset_symbol: str | None = None


def score_all(inputs: Inputs, config: RiskConfig | None = None) -> dict[str, Assessment]:
    """Score every node in the trace, not only the root.

    Node-level scoring is what makes the graph readable at a glance and what surfaces the
    intermediary wallets worth naming in a report. The root is scored independently
    rather than as an aggregate of its downstream nodes — but it does inherit Group A
    contact, hop-scaled, which models the real investigative intuition.
    """
    config = config or active()
    contacts = _contacts(inputs)
    return {
        address: score(
            SignalInput(
                address=address,
                features=inputs.features.get(address),
                attribution=inputs.attributions.get(address),
                patterns=[f for f in inputs.findings if f.subject_address == address],
                contacts=contacts.get(address, []),
                tainted_amount_raw=node.tainted_raw,
                asset_symbol=inputs.asset_symbol,
                cross_case_match=inputs.cross_case.get(address),
            ),
            confidence=_confidence(address, inputs, config),
            config=config,
        )
        for address, node in inputs.trace.nodes.items()
    }


def score(data: SignalInput, confidence: float, config: RiskConfig | None = None) -> Assessment:
    """Evaluate every enabled signal and add up the points."""
    config = config or active()
    evaluated: list[Signal] = []
    skipped: list[NotEvaluated] = []

    service = _confirmed_service(data.attribution)
    for name, evaluate in signal_module.REGISTRY.items():
        signal_config = config.signal(name)
        if signal_config is None:
            continue
        if service is not None and signal_config.group in BEHAVIOURAL_GROUPS:
            skipped.append(
                NotEvaluated(
                    name,
                    f"{data.address} is a confirmed {str(service).lower()}"
                    f"; this behaviour describes the service, not a suspect.",
                )
            )
            continue
        outcome = evaluate(data, signal_config)
        (evaluated if isinstance(outcome, Signal) else skipped).append(outcome)  # type: ignore[arg-type]

    raw = sum(signal.points for signal in evaluated)
    total = min(100, round(raw))
    return Assessment(
        address=data.address,
        score=total,
        band=config.band_for(total),
        confidence=confidence,
        # Highest contribution first: the breakdown should open with the reason.
        signals=sorted(evaluated, key=lambda s: (-s.points, s.name)),
        not_evaluated=sorted(skipped, key=lambda n: n.name),
        config_version=config.version,
    )


def _confirmed_service(attribution: AttributionResult | None) -> EntityType | None:
    if (
        attribution is not None
        and attribution.tier is AttributionTier.CONFIRMED
        and attribution.entity_type in BEHAVIOUR_IS_THE_SERVICE
    ):
        return attribution.entity_type
    return None


def _contacts(inputs: Inputs) -> dict[str, list[RiskContact]]:
    """For each node, the risky entities its value reached and how many hops away.

    Distance is measured *forward* along the graph: a node is implicated by what it sends
    to, not by what happens to sit upstream of it. An address three hops downstream of a
    mixer did not use the mixer.
    """
    risky = {
        address: result
        for address, result in inputs.attributions.items()
        if result.entity_type in CONTACT_TYPES and result.tier is AttributionTier.CONFIRMED
    }
    if not risky:
        return {}

    found: dict[str, list[RiskContact]] = {}
    for address in inputs.trace.nodes:
        if address not in inputs.graph:
            continue
        reached = []
        for target, result in risky.items():
            hops = _hops(inputs.graph, address, target)
            if hops is None:
                continue
            reached.append(
                RiskContact(
                    address=target,
                    entity_type=result.entity_type,
                    entity_name=result.entity_name,
                    hops=hops,
                    tx_hashes=_hashes_towards(inputs.trace, address, target),
                )
            )
        if reached:
            found[address] = reached
    return found


def _hops(graph: TraceGraph, source: str, target: str) -> int | None:
    from app.graph.algorithms import shortest_path

    path = shortest_path(graph, source, target)
    return None if path is None else len(path) - 1


def _hashes_towards(trace: TraceResult, source: str, target: str) -> list[str]:
    """The transactions leaving `source`, so a finding links straight to evidence."""
    direct = [
        e.tx_hashes for e in trace.edges if e.from_address == source and e.to_address == target
    ]
    if direct:
        return direct[0][:5]
    return [h for e in trace.edges if e.from_address == source for h in e.tx_hashes][:5]


def _confidence(address: str, inputs: Inputs, config: RiskConfig) -> float:
    """How much the score can be relied on — reported alongside it, never folded in."""
    weights = config.confidence

    data_completeness = 1.0 if inputs.data_complete else 0.5

    attribution = inputs.attributions.get(address)
    if attribution is None:
        attribution_quality = 0.5
    elif attribution.tier is AttributionTier.CONFIRMED:
        attribution_quality = 1.0
    elif attribution.tier is AttributionTier.PROBABLE:
        attribution_quality = float(attribution.confidence or 0.5)
    else:
        attribution_quality = 0.6

    node = inputs.trace.nodes.get(address)
    if node is None or not node.is_terminal:
        trace_completeness = 0.8
    elif node.termination_reason in INCOMPLETE_TERMINATIONS:
        trace_completeness = 0.4
    else:
        trace_completeness = 1.0

    return (
        weights.data_completeness * data_completeness
        + weights.attribution_quality * attribution_quality
        + weights.trace_completeness * trace_completeness
    )
