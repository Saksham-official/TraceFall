import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models._types import RawAmount, pg_enum
from app.db.models.enums import AddressRole, CaseStatus, Priority


class Case(Base):
    """No victim PII is stored — reference numbers only (ADR-011)."""

    __tablename__ = "cases"
    __table_args__ = (Index("ix_cases_owner_status_created", "owner_id", "status", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    case_number: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    ncrp_reference: Mapped[str | None] = mapped_column(String(64), index=True)
    fir_reference: Mapped[str | None] = mapped_column(String(64), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    reported_loss_inr: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    incident_date: Mapped[date | None] = mapped_column()
    status: Mapped[CaseStatus] = mapped_column(
        pg_enum(CaseStatus, "case_status"), nullable=False, server_default=CaseStatus.OPEN
    )
    priority: Mapped[Priority] = mapped_column(
        pg_enum(Priority, "priority"), nullable=False, server_default=Priority.MEDIUM
    )
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=False
    )
    closed_at: Mapped[datetime | None] = mapped_column()


class CaseAssignment(Base):
    """Case isolation is by ownership or explicit assignment (NFR-08)."""

    __tablename__ = "case_assignments"
    __table_args__ = (UniqueConstraint("case_id", "user_id", name="case_id_user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    assigned_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)


class CaseAddress(Base):
    """Links a case to a suspect address, with the context that anchors the trace."""

    __tablename__ = "case_addresses"
    __table_args__ = (
        UniqueConstraint("case_id", "address_id", "role", name="case_id_address_id_role"),
        Index("ix_case_addresses_address_id", "address_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False
    )
    address_id: Mapped[int] = mapped_column(ForeignKey("addresses.id"), nullable=False)
    role: Mapped[AddressRole] = mapped_column(pg_enum(AddressRole, "address_role"), nullable=False)
    reported_amount_raw: Mapped[Decimal | None] = mapped_column(RawAmount)
    reported_asset_id: Mapped[int | None] = mapped_column(ForeignKey("assets.id"))
    reported_at: Mapped[datetime | None] = mapped_column()
    anchor_tx_hash: Mapped[str | None] = mapped_column(String(128))
    notes: Mapped[str | None] = mapped_column(Text)
    added_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    added_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)


class CaseNote(Base):
    __tablename__ = "case_notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    pinned_finding_type: Mapped[str | None] = mapped_column(String(64))
    pinned_finding_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)


class CaseTimelineEvent(Base):
    """User-visible case narrative. Distinct from audit_log, which is a security artefact."""

    __tablename__ = "case_timeline"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
