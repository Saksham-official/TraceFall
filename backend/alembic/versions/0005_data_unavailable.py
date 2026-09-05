"""a trace can end because retrieval could not answer

A branch that ends because the address could not be fetched is not the same finding as
one that ends because the funds stopped moving. See ADR-019 and OQ-18.

Revision ID: 0005_data_unavailable
Revises: 0004_reported_amount
Create Date: 2026-09-05
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005_data_unavailable"
down_revision: str | None = "0004_reported_amount"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Transactional on PostgreSQL 12 and later, provided the new value is not used in
    # the same transaction that adds it.
    op.execute("ALTER TYPE termination_reason ADD VALUE IF NOT EXISTS 'DATA_UNAVAILABLE'")


def downgrade() -> None:
    # PostgreSQL cannot drop a value from an enum. Rebuilding the type would mean
    # rewriting every column that uses it, which is not worth it to undo an addition;
    # the value simply stops being written.
    pass
