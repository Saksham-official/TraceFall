"""seed chains and native assets, and add the case-number sequence

Revision ID: 0003_reference_data
Revises: 0002_append_only
Create Date: 2026-09-05
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003_reference_data"
down_revision: str | None = "0002_append_only"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # A sequence, so concurrent case creation cannot collide on the human-readable number.
    op.execute("CREATE SEQUENCE case_number_seq START WITH 1;")
    op.execute(
        """
        INSERT INTO chains (id, code, name, explorer_url_template, address_format, is_enabled)
        VALUES
            (1, 'TRON', 'TRON', 'https://tronscan.org/#/transaction/{tx_hash}', 'base58check', true),
            (2, 'ETHEREUM', 'Ethereum', 'https://etherscan.io/tx/{tx_hash}', 'hex', true);
        """
    )
    # Native currency is an ordinary asset row; this removes branching from every consumer.
    op.execute(
        """
        INSERT INTO assets (chain_id, contract_address, symbol, name, decimals,
                            is_native, is_stablecoin)
        VALUES
            (1, NULL, 'TRX', 'TRON', 6, true, false),
            (2, NULL, 'ETH', 'Ether', 18, true, false);
        """
    )


def downgrade() -> None:
    op.execute("DROP SEQUENCE IF EXISTS case_number_seq;")
    op.execute("DELETE FROM assets WHERE is_native = true AND chain_id IN (1, 2);")
    op.execute("DELETE FROM chains WHERE id IN (1, 2);")
