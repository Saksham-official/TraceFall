import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    String,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models._types import pg_enum
from app.db.models.enums import EvidenceType, NarrativeSource, ReportFormat, ReportType


class EvidenceItem(Base):
    """Catalogue of the immutable evidence layer. Bodies live on disk; this indexes them.

    Append-only: the application role is granted INSERT and SELECT only (see migration).
    """

    __tablename__ = "evidence_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id"), nullable=False, index=True)
    analysis_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("analysis_runs.id"))
    evidence_type: Mapped[EvidenceType] = mapped_column(
        pg_enum(EvidenceType, "evidence_type"), nullable=False
    )
    provider: Mapped[str | None] = mapped_column(String(64))
    endpoint: Mapped[str | None] = mapped_column(String(500))
    request_params: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    http_status: Mapped[int | None] = mapped_column()
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    byte_size: Mapped[int | None] = mapped_column(BigInteger)
    retrieved_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    # Distinguishes a cached snapshot from live data (NFR-15).
    is_fixture: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    analysis_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("analysis_runs.id"))
    report_type: Mapped[ReportType] = mapped_column(
        pg_enum(ReportType, "report_type"), nullable=False
    )
    format: Mapped[ReportFormat] = mapped_column(
        pg_enum(ReportFormat, "report_format"), nullable=False
    )
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    generated_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    # Recorded so a reader knows whether prose was machine-written (FR-115).
    narrative_source: Mapped[NarrativeSource] = mapped_column(
        pg_enum(NarrativeSource, "narrative_source"), nullable=False
    )
    generated_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
