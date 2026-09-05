"""The detector framework.

A detector is an independent function over one subject. It declares its thresholds and,
**mandatorily, what it gets wrong** — a detector that cannot state its false positives
cannot be registered, which is FR-66 enforced by the registry rather than by review.

Two properties matter more than the detectors themselves:

**Isolation.** A detector that raises degrades to "detector unavailable" and the rest of
the stage continues. One bad regex must not cost an investigator every other finding.

**Explainability.** Every finding carries a plain-language sentence, the transactions that
triggered it, and the note about what else produces this shape. A pattern presented
without its false positives will be read as a conclusion.
"""

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.db.models.enums import PatternType, Severity
from app.graph.builder import TraceGraph
from app.normalize.transfer import NormalizedTransfer

log = logging.getLogger(__name__)

DETECTOR_VERSION = "1.0.0"


@dataclass(frozen=True, slots=True)
class Subject:
    """What every detector is given: the flow, and the transfers behind it."""

    graph: TraceGraph
    transfers: dict[str, list[NormalizedTransfer]]

    def touching(self, address: str) -> list[NormalizedTransfer]:
        return [t for t in self.transfers.get(address, []) if t.succeeded]

    def inbound(self, address: str) -> list[NormalizedTransfer]:
        return sorted(
            (t for t in self.touching(address) if t.to_address == address),
            key=lambda t: (t.block_time, t.tx_hash),
        )

    def outbound(self, address: str) -> list[NormalizedTransfer]:
        return sorted(
            (t for t in self.touching(address) if t.from_address == address),
            key=lambda t: (t.block_time, t.tx_hash),
        )


@dataclass(frozen=True)
class Finding:
    pattern_type: PatternType
    severity: Severity
    subject_address: str
    explanation: str
    involved_addresses: list[str] = field(default_factory=list)
    trigger_tx_hashes: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    # Filled in by the runner from the detector's declaration, so a finding can never
    # reach an investigator without it.
    false_positive_note: str = ""
    detector_version: str = DETECTOR_VERSION


@dataclass(frozen=True)
class Detector:
    pattern_type: PatternType
    config: dict[str, Any]
    false_positive_note: str
    run: Callable[[Subject, dict[str, Any]], list[Finding]]


@dataclass
class StageResult:
    """Findings, plus an honest account of any detector that could not run."""

    findings: list[Finding] = field(default_factory=list)
    unavailable: list[dict[str, str]] = field(default_factory=list)

    @property
    def degraded(self) -> bool:
        return bool(self.unavailable)


REGISTRY: list[Detector] = []


def register(
    pattern_type: PatternType, config: dict[str, Any], false_positive_note: str
) -> Callable[[Callable[[Subject, dict[str, Any]], list[Finding]]], Detector]:
    """Declare a detector. An empty false-positive note is a registration error.

    This is the generic enforcement of FR-66: a new detector cannot ship without saying
    what else produces its shape, and no reviewer has to remember to ask.
    """

    def wrap(fn: Callable[[Subject, dict[str, Any]], list[Finding]]) -> Detector:
        if not false_positive_note.strip():
            raise ValueError(
                f"{pattern_type} declares no false_positive_note. A detector that cannot "
                f"state what else produces its shape cannot be registered (FR-66)."
            )
        detector = Detector(pattern_type, dict(config), false_positive_note.strip(), fn)
        REGISTRY.append(detector)
        return detector

    return wrap


def run_all(subject: Subject, detectors: Sequence[Detector] | None = None) -> StageResult:
    """Run every detector in isolation.

    A detector that raises is recorded as unavailable and the stage continues — a partial
    set of findings with the gap stated beats no findings at all.
    """
    result = StageResult()
    for detector in detectors if detectors is not None else REGISTRY:
        try:
            found = detector.run(subject, detector.config)
        except Exception as exc:  # noqa: BLE001 — isolation is the whole point
            log.exception("detector %s failed", detector.pattern_type)
            result.unavailable.append(
                {"pattern_type": str(detector.pattern_type), "reason": repr(exc)}
            )
            continue
        for finding in found:
            result.findings.append(
                Finding(
                    **{
                        **finding.__dict__,
                        "false_positive_note": detector.false_positive_note,
                    }
                )
            )
    result.findings.sort(key=lambda f: (str(f.pattern_type), f.subject_address))
    return result


def severity_from(value: float, medium: float, high: float) -> Severity:
    """Shared magnitude mapping, so 'HIGH' means the same thing across detectors."""
    if value >= high:
        return Severity.HIGH
    if value >= medium:
        return Severity.MEDIUM
    return Severity.LOW
