"""keep the branches a trace did not follow

A trace prunes branches below the taint threshold, past the fan-out cap, or as dust, and
principle 12 requires an investigator to see what was not followed. Those branches lived
only in memory, so a graph rebuilt from the database silently lost them — and the
accounting invariant could not be re-checked from stored rows either.

Revision ID: 0006_pruned_branches
Revises: 0005_data_unavailable
Create Date: 2026-09-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0006_pruned_branches"
down_revision: str | None = "0005_data_unavailable"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "traces",
        sa.Column("pruned", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.add_column(
        "traces",
        sa.Column("unavailable", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.add_column(
        "trace_nodes",
        sa.Column("pruned_amount_raw", sa.Numeric(78, 0), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("trace_nodes", "pruned_amount_raw")
    op.drop_column("traces", "unavailable")
    op.drop_column("traces", "pruned")
