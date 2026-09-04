import uuid
from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Index, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuditLog(Base):
    """Append-only security record.

    Reads are audited as well as writes: in an investigation system, who looked at which
    case is itself security-relevant (ADR-013). Append-only is enforced by database
    grants, not by application discipline — see the initial migration.
    """

    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_case_created", "case_id", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(64))
    case_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    request_id: Mapped[str | None] = mapped_column(String(64), index=True)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(300))
    payload_sha256: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
