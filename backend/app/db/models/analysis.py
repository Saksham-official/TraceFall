import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models._types import Fraction, RawAmount, pg_enum
from app.db.models.enums import (
    AnalysisStage,
    AnalysisStatus,
    TaintModel,
    TerminationReason,
    TraceDirection,
)


class AnalysisRun(Base):
    """Every derived artefact hangs off a run. Re-running creates a new one (FR-124)."""

    __tablename__ = "analysis_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    root_address_id: Mapped[int] = mapped_column(ForeignKey("addresses.id"), nullable=False)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    status: Mapped[AnalysisStatus] = mapped_column(
        pg_enum(AnalysisStatus, "analysis_status"), nullable=False
    )
    stage: Mapped[AnalysisStage | None] = mapped_column(pg_enum(AnalysisStage, "analysis_stage"))
    progress_pct: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    # Which stages ran partially and why (FR-122).
    degradations: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, server_default="[]")
    engine_versions: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    started_at: Mapped[datetime | None] = mapped_column()
    completed_at: Mapped[datetime | None] = mapped_column()
    heartbeat_at: Mapped[datetime | None] = mapped_column()
    error: Mapped[str | None] = mapped_column(Text)
    triggered_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)


class Trace(Base):
    __tablename__ = "traces"

    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    root_address_id: Mapped[int] = mapped_column(ForeignKey("addresses.id"), nullable=False)
    direction: Mapped[TraceDirection] = mapped_column(
        pg_enum(TraceDirection, "trace_direction"), nullable=False
    )
    anchor_tx_hash: Mapped[str | None] = mapped_column(String(128))
    max_depth: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    taint_threshold: Mapped[Decimal] = mapped_column(Fraction, nullable=False)
    edge_budget: Mapped[int] = mapped_column(Integer, nullable=False)
    taint_model: Mapped[TaintModel] = mapped_column(
        pg_enum(TaintModel, "taint_model"), nullable=False
    )
    node_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    edge_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    total_traced_raw: Mapped[Decimal | None] = mapped_column(RawAmount)
    computed_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)


class TraceNode(Base):
    __tablename__ = "trace_nodes"
    __table_args__ = (
        UniqueConstraint("trace_id", "address_id", name="trace_id_address_id"),
        Index("ix_trace_nodes_trace_depth", "trace_id", "depth"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    trace_id: Mapped[int] = mapped_column(
        ForeignKey("traces.id", ondelete="CASCADE"), nullable=False
    )
    address_id: Mapped[int] = mapped_column(ForeignKey("addresses.id"), nullable=False)
    depth: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    # Fraction of the original tainted value attributed here (haircut model).
    taint_share: Mapped[Decimal] = mapped_column(Fraction, nullable=False)
    tainted_amount_raw: Mapped[Decimal] = mapped_column(RawAmount, nullable=False)
    is_terminal: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    termination_reason: Mapped[TerminationReason | None] = mapped_column(
        pg_enum(TerminationReason, "termination_reason")
    )
    first_reached_at: Mapped[datetime | None] = mapped_column()


class TraceEdge(Base):
    """Aggregated flow between an address pair, not an individual transfer.

    tx_hashes is the drill-down path back to the canonical layer — no finding may
    dead-end without a route to raw evidence.
    """

    __tablename__ = "trace_edges"
    __table_args__ = (
        UniqueConstraint(
            "trace_id",
            "from_address_id",
            "to_address_id",
            "asset_id",
            name="trace_id_from_address_id_to_address_id_asset_id",
        ),
        Index("ix_trace_edges_trace_id", "trace_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    trace_id: Mapped[int] = mapped_column(
        ForeignKey("traces.id", ondelete="CASCADE"), nullable=False
    )
    from_address_id: Mapped[int] = mapped_column(ForeignKey("addresses.id"), nullable=False)
    to_address_id: Mapped[int] = mapped_column(ForeignKey("addresses.id"), nullable=False)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), nullable=False)
    total_amount_raw: Mapped[Decimal] = mapped_column(RawAmount, nullable=False)
    tainted_amount_raw: Mapped[Decimal] = mapped_column(RawAmount, nullable=False)
    transfer_count: Mapped[int] = mapped_column(Integer, nullable=False)
    first_transfer_at: Mapped[datetime | None] = mapped_column()
    last_transfer_at: Mapped[datetime | None] = mapped_column()
    tx_hashes: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, server_default="[]")
