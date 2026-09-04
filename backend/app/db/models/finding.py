import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models._types import Fraction, pg_enum
from app.db.models.enums import AlertType, PatternType, RiskBand, Severity


class PatternFinding(Base):
    __tablename__ = "pattern_findings"

    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    pattern_type: Mapped[PatternType] = mapped_column(
        pg_enum(PatternType, "pattern_type"), nullable=False
    )
    severity: Mapped[Severity] = mapped_column(pg_enum(Severity, "severity"), nullable=False)
    subject_address_id: Mapped[int] = mapped_column(ForeignKey("addresses.id"), nullable=False)
    involved_address_ids: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    trigger_tx_hashes: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, server_default="[]")
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    # Mandatory (FR-66): a detector that cannot state its false positives cannot ship.
    false_positive_note: Mapped[str] = mapped_column(Text, nullable=False)
    detector_version: Mapped[str] = mapped_column(String(32), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)


class RiskAssessment(Base):
    """The signals array is the explainability payload and is not optional (FR-81)."""

    __tablename__ = "risk_assessments"
    __table_args__ = (
        UniqueConstraint("analysis_run_id", "address_id", name="analysis_run_id_address_id"),
        CheckConstraint("score >= 0 AND score <= 100", name="score_range"),
        CheckConstraint("confidence > 0 AND confidence <= 1", name="confidence_range"),
        CheckConstraint(
            "jsonb_typeof(signals) = 'array' AND jsonb_array_length(signals) > 0",
            name="signals_not_empty",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False
    )
    address_id: Mapped[int] = mapped_column(ForeignKey("addresses.id"), nullable=False)
    score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    band: Mapped[RiskBand] = mapped_column(pg_enum(RiskBand, "risk_band"), nullable=False)
    # Reported separately, never multiplied into the score (FR-83).
    confidence: Mapped[Decimal] = mapped_column(Fraction, nullable=False)
    signals: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    not_evaluated: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, server_default="[]")
    config_version: Mapped[str] = mapped_column(String(64), nullable=False)
    engine_version: Mapped[str] = mapped_column(String(32), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        Index(
            "ix_alerts_open",
            "case_id",
            "created_at",
            postgresql_where=text("acknowledged_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False
    )
    analysis_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="CASCADE")
    )
    alert_type: Mapped[AlertType] = mapped_column(pg_enum(AlertType, "alert_type"), nullable=False)
    severity: Mapped[Severity] = mapped_column(pg_enum(Severity, "severity"), nullable=False)
    address_id: Mapped[int | None] = mapped_column(ForeignKey("addresses.id"))
    trigger_reason: Mapped[str] = mapped_column(Text, nullable=False)
    source_finding_type: Mapped[str | None] = mapped_column(String(64))
    source_finding_id: Mapped[str | None] = mapped_column(String(64))
    acknowledged_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    acknowledged_at: Mapped[datetime | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
