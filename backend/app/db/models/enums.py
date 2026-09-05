"""Enumerations shared across the schema.

Values are stored as native PostgreSQL enum types so the database rejects an invalid
value rather than trusting application discipline.
"""

from enum import StrEnum


class UserRole(StrEnum):
    ADMIN = "ADMIN"
    INVESTIGATOR = "INVESTIGATOR"
    ANALYST = "ANALYST"
    VIEWER = "VIEWER"


class CaseStatus(StrEnum):
    OPEN = "OPEN"
    ANALYSING = "ANALYSING"
    REVIEW = "REVIEW"
    CLOSED = "CLOSED"


class Priority(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AddressRole(StrEnum):
    SUSPECT = "SUSPECT"
    VICTIM_SOURCE = "VICTIM_SOURCE"
    DISCOVERED = "DISCOVERED"


class ChainCode(StrEnum):
    TRON = "TRON"
    ETHEREUM = "ETHEREUM"


class EntityType(StrEnum):
    EXCHANGE = "EXCHANGE"
    MIXER = "MIXER"
    BRIDGE = "BRIDGE"
    TOKEN_CONTRACT = "TOKEN_CONTRACT"  # noqa: S105  # entity type, not a credential
    DEFI = "DEFI"
    GAMBLING = "GAMBLING"
    SANCTIONED = "SANCTIONED"
    MERCHANT = "MERCHANT"
    UNKNOWN = "UNKNOWN"


class AttributionTier(StrEnum):
    """The product's central integrity distinction. See docs/VASP_IDENTIFICATION.md."""

    CONFIRMED = "CONFIRMED"
    PROBABLE = "PROBABLE"
    UNATTRIBUTED = "UNATTRIBUTED"


class AttributionMethod(StrEnum):
    DATASET_MATCH = "DATASET_MATCH"
    DEPOSIT_HEURISTIC = "DEPOSIT_HEURISTIC"
    CLASSIFIER = "CLASSIFIER"
    MANUAL = "MANUAL"


class LabelReliability(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class TransferStatus(StrEnum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    REVERTED = "REVERTED"
    # Unconfirmed transfers are ingested but excluded from risk scoring; a score that
    # changes when a transaction fails to confirm is not defensible.
    PENDING = "PENDING"


class AnalysisStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class AnalysisStage(StrEnum):
    RETRIEVAL = "RETRIEVAL"
    NORMALIZATION = "NORMALIZATION"
    ENRICHMENT = "ENRICHMENT"
    TRACING = "TRACING"
    GRAPH = "GRAPH"
    PATTERNS = "PATTERNS"
    ATTRIBUTION = "ATTRIBUTION"
    RISK = "RISK"
    ALERTS = "ALERTS"


class TraceDirection(StrEnum):
    FORWARD = "FORWARD"
    BACKWARD = "BACKWARD"


class TaintModel(StrEnum):
    """Recorded per trace so a future FIFO option stays distinguishable (ADR-004)."""

    HAIRCUT = "HAIRCUT"


class TerminationReason(StrEnum):
    MAX_DEPTH = "MAX_DEPTH"
    BELOW_THRESHOLD = "BELOW_THRESHOLD"
    SERVICE_BOUNDARY = "SERVICE_BOUNDARY"
    NO_OUTFLOW = "NO_OUTFLOW"
    EDGE_BUDGET = "EDGE_BUDGET"
    TIME_WINDOW = "TIME_WINDOW"
    # Not a finding: the branch ended because retrieval could not answer, which is a
    # different statement from "nothing left this address" (ADR-019).
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"


class PatternType(StrEnum):
    FAN_OUT = "FAN_OUT"
    FAN_IN = "FAN_IN"
    RAPID_TRANSFER = "RAPID_TRANSFER"
    PEEL_CHAIN = "PEEL_CHAIN"
    DORMANCY_BURST = "DORMANCY_BURST"
    STRUCTURING = "STRUCTURING"


class Severity(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class RiskBand(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AlertType(StrEnum):
    SANCTIONED_CONTACT = "SANCTIONED_CONTACT"
    MIXER_CONTACT = "MIXER_CONTACT"
    CRITICAL_RISK = "CRITICAL_RISK"
    CROSS_CASE_MATCH = "CROSS_CASE_MATCH"


class EvidenceType(StrEnum):
    API_RESPONSE = "API_RESPONSE"
    REPORT = "REPORT"
    GRAPH_IMAGE = "GRAPH_IMAGE"


class ReportType(StrEnum):
    FULL = "FULL"
    SUMMARY = "SUMMARY"


class ReportFormat(StrEnum):
    PDF = "PDF"
    JSON = "JSON"
    CSV = "CSV"


class NarrativeSource(StrEnum):
    TEMPLATE = "TEMPLATE"
    LLM = "LLM"
