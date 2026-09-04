import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models._types import Fraction, RawAmount, pg_enum
from app.db.models.enums import (
    AttributionMethod,
    AttributionTier,
    EntityType,
    LabelReliability,
)


class Entity(Base):
    __tablename__ = "entities"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    entity_type: Mapped[EntityType] = mapped_column(
        pg_enum(EntityType, "entity_type"), nullable=False
    )
    website: Mapped[str | None] = mapped_column(String(255))
    jurisdiction: Mapped[str | None] = mapped_column(String(100))
    # Tri-state: "we don't know" must stay distinguishable from "no" (FR-77).
    is_fiu_ind_registered: Mapped[bool | None] = mapped_column(Boolean)
    is_sanctioned: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    # How an investigator would actually reach them — the operationally useful field.
    contact_channel: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)


class LabelSource(Base):
    """Provenance for every label. Without this table, CONFIRMED means nothing."""

    __tablename__ = "label_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    url: Mapped[str | None] = mapped_column(String(500))
    licence: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    reliability: Mapped[LabelReliability] = mapped_column(
        pg_enum(LabelReliability, "label_reliability"), nullable=False
    )
    ingested_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    dataset_date: Mapped[date | None] = mapped_column()
    record_count: Mapped[int | None] = mapped_column(Integer)


class AddressLabel(Base):
    """Conflicting labels from different sources are stored, not resolved (FR-75)."""

    __tablename__ = "address_labels"
    __table_args__ = (
        UniqueConstraint(
            "address_id",
            "label_source_id",
            "label_text",
            name="address_id_label_source_id_label_text",
        ),
        Index("ix_address_labels_address_id", "address_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    address_id: Mapped[int] = mapped_column(ForeignKey("addresses.id"), nullable=False)
    entity_id: Mapped[int | None] = mapped_column(ForeignKey("entities.id"))
    label_source_id: Mapped[int] = mapped_column(ForeignKey("label_sources.id"), nullable=False)
    label_text: Mapped[str] = mapped_column(String(300), nullable=False)
    label_type: Mapped[str | None] = mapped_column(String(64))
    # NULL means the source asserts the label flatly, with no confidence of its own.
    confidence: Mapped[Decimal | None] = mapped_column(Fraction)
    ingested_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)


class AddressProfile(Base):
    """Derived statistics, keyed by data freshness so a stale profile is never reused."""

    __tablename__ = "address_profiles"
    __table_args__ = (
        UniqueConstraint("address_id", "data_version", name="address_id_data_version"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    address_id: Mapped[int] = mapped_column(ForeignKey("addresses.id"), nullable=False)
    data_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    tx_count_in: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    tx_count_out: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    unique_counterparties_in: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    unique_counterparties_out: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    total_in_raw: Mapped[Decimal | None] = mapped_column(RawAmount)
    total_out_raw: Mapped[Decimal | None] = mapped_column(RawAmount)
    balance_raw: Mapped[Decimal | None] = mapped_column(RawAmount)
    age_days: Mapped[int | None] = mapped_column(Integer)
    active_days: Mapped[int | None] = mapped_column(Integer)
    median_dwell_seconds: Mapped[int | None] = mapped_column(BigInteger)
    sweep_ratio: Mapped[Decimal | None] = mapped_column(Fraction)
    distinct_assets: Mapped[int | None] = mapped_column(Integer)
    # Full behavioural feature vector; features evolve and do not each deserve a migration.
    features: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")


class Attribution(Base):
    """The system's tiered conclusion about an address.

    The CHECK constraint below is the product's central integrity rule. It lives in the
    database rather than in application code because application discipline erodes and
    constraints do not (ADR-005).
    """

    __tablename__ = "attributions"
    __table_args__ = (
        CheckConstraint(
            "("
            " tier = 'CONFIRMED' AND entity_id IS NOT NULL AND confidence IS NULL"
            " AND jsonb_typeof(evidence) = 'array' AND jsonb_array_length(evidence) > 0"
            ") OR ("
            " tier = 'PROBABLE' AND confidence IS NOT NULL AND confidence > 0 AND confidence <= 1"
            " AND jsonb_typeof(evidence) = 'array' AND jsonb_array_length(evidence) > 0"
            ") OR ("
            " tier = 'UNATTRIBUTED' AND entity_id IS NULL AND confidence IS NULL"
            ")",
            name="tier_requires_evidence",
        ),
        Index("ix_attributions_address_computed", "address_id", "computed_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    address_id: Mapped[int] = mapped_column(ForeignKey("addresses.id"), nullable=False)
    entity_id: Mapped[int | None] = mapped_column(ForeignKey("entities.id"))
    entity_type: Mapped[EntityType] = mapped_column(
        pg_enum(EntityType, "entity_type"), nullable=False
    )
    tier: Mapped[AttributionTier] = mapped_column(
        pg_enum(AttributionTier, "attribution_tier"), nullable=False
    )
    confidence: Mapped[Decimal | None] = mapped_column(Fraction)
    method: Mapped[AttributionMethod] = mapped_column(
        pg_enum(AttributionMethod, "attribution_method"), nullable=False
    )
    evidence: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, server_default="[]")
    engine_version: Mapped[str] = mapped_column(String(32), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)


class AttributionOverride(Base):
    """Investigator judgement, kept strictly separate from machine output (FR-78)."""

    __tablename__ = "attribution_overrides"

    id: Mapped[int] = mapped_column(primary_key=True)
    attribution_id: Mapped[int] = mapped_column(
        ForeignKey("attributions.id", ondelete="CASCADE"), nullable=False
    )
    address_id: Mapped[int] = mapped_column(ForeignKey("addresses.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    override_tier: Mapped[AttributionTier] = mapped_column(
        pg_enum(AttributionTier, "attribution_tier"), nullable=False
    )
    override_entity_id: Mapped[int | None] = mapped_column(ForeignKey("entities.id"))
    justification: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
