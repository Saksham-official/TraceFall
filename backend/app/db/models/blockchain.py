from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models._types import RawAmount, pg_enum
from app.db.models.enums import ChainCode, TransferStatus


class Chain(Base):
    """Reference table rather than an enum, so a chain can be added without a migration."""

    __tablename__ = "chains"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    code: Mapped[ChainCode] = mapped_column(pg_enum(ChainCode, "chain_code"), unique=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    explorer_url_template: Mapped[str] = mapped_column(String(255), nullable=False)
    address_format: Mapped[str] = mapped_column(String(32), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")


class Asset(Base):
    """Native currency is an ordinary row; this removes branching from every consumer."""

    __tablename__ = "assets"
    __table_args__ = (
        UniqueConstraint("chain_id", "contract_address", name="chain_id_contract_address"),
        # Exactly one native asset per chain.
        Index(
            "ix_assets_native_unique",
            "chain_id",
            unique=True,
            postgresql_where=text("is_native"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    chain_id: Mapped[int] = mapped_column(ForeignKey("chains.id"), nullable=False)
    contract_address: Mapped[str | None] = mapped_column(String(64))
    symbol: Mapped[str | None] = mapped_column(String(32))
    name: Mapped[str | None] = mapped_column(String(128))
    decimals: Mapped[int | None] = mapped_column(SmallInteger)
    is_native: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    is_stablecoin: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    first_seen_at: Mapped[datetime | None] = mapped_column()


class Address(Base):
    """Stored once and shared across cases; cross-case correlation is then a join."""

    __tablename__ = "addresses"
    __table_args__ = (UniqueConstraint("chain_id", "address", name="chain_id_address"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    chain_id: Mapped[int] = mapped_column(ForeignKey("chains.id"), nullable=False)
    address: Mapped[str] = mapped_column(String(64), nullable=False)
    # Tri-state: NULL means "not checked yet", which is different from "not a contract".
    is_contract: Mapped[bool | None] = mapped_column(Boolean)
    first_seen_block: Mapped[int | None] = mapped_column(BigInteger)
    first_seen_at: Mapped[datetime | None] = mapped_column()
    last_seen_at: Mapped[datetime | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (UniqueConstraint("chain_id", "tx_hash", name="chain_id_tx_hash"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    chain_id: Mapped[int] = mapped_column(ForeignKey("chains.id"), nullable=False)
    tx_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    block_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    block_time: Mapped[datetime] = mapped_column(nullable=False, index=True)
    from_address_id: Mapped[int] = mapped_column(ForeignKey("addresses.id"), nullable=False)
    to_address_id: Mapped[int | None] = mapped_column(ForeignKey("addresses.id"))
    fee_raw: Mapped[Decimal | None] = mapped_column(RawAmount)
    status: Mapped[TransferStatus] = mapped_column(
        pg_enum(TransferStatus, "transfer_status"), nullable=False
    )
    nonce: Mapped[int | None] = mapped_column(BigInteger)
    input_size: Mapped[int | None] = mapped_column(Integer)
    ingested_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)


class Transfer(Base):
    """One row per value movement, not per transaction.

    A single transaction moving ETH and emitting three ERC-20 events is four rows sharing
    one tx_hash. This keeps the tracing engine uniform: it only ever sees value moving
    between two addresses.
    """

    __tablename__ = "transfers"
    __table_args__ = (
        UniqueConstraint(
            "chain_id", "tx_hash", "transfer_index", name="chain_id_tx_hash_transfer_index"
        ),
        Index("ix_transfers_from_time", "from_address_id", "block_time"),
        Index("ix_transfers_to_time", "to_address_id", "block_time"),
        Index("ix_transfers_pair_time", "from_address_id", "to_address_id", "block_time"),
        Index("ix_transfers_chain_hash", "chain_id", "tx_hash"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    transaction_id: Mapped[int] = mapped_column(ForeignKey("transactions.id"), nullable=False)
    chain_id: Mapped[int] = mapped_column(ForeignKey("chains.id"), nullable=False)
    tx_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    transfer_index: Mapped[int] = mapped_column(Integer, nullable=False)
    block_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    block_time: Mapped[datetime] = mapped_column(nullable=False)
    from_address_id: Mapped[int] = mapped_column(ForeignKey("addresses.id"), nullable=False)
    to_address_id: Mapped[int] = mapped_column(ForeignKey("addresses.id"), nullable=False)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), nullable=False)
    amount_raw: Mapped[Decimal] = mapped_column(RawAmount, nullable=False)
    # Denormalised deliberately: token metadata can change, a historical transfer must not.
    decimals: Mapped[int | None] = mapped_column(SmallInteger)
    usd_value_approx: Mapped[Decimal | None] = mapped_column(RawAmount)
    status: Mapped[TransferStatus] = mapped_column(
        pg_enum(TransferStatus, "transfer_status"), nullable=False
    )
    is_internal: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    ingested_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
