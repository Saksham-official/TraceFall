"""store the victim's reported amount as given

The trace anchor (FR-41) needs the amount and time the victim sent funds. The existing
columns hold raw integer units, which require the token's decimals — unknown at intake
and never to be guessed. These columns keep what the victim actually reported.

Revision ID: 0004_reported_amount
Revises: 0003_reference_data
Create Date: 2026-09-05
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_reported_amount"
down_revision: str | None = "0003_reference_data"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("case_addresses", sa.Column("reported_amount", sa.Numeric(38, 18), nullable=True))
    op.add_column(
        "case_addresses", sa.Column("reported_asset_symbol", sa.String(32), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("case_addresses", "reported_asset_symbol")
    op.drop_column("case_addresses", "reported_amount")
