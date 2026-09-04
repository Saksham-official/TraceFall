"""append-only triggers for audit_log and evidence_items

Revision ID: 0002_append_only
Revises:
Create Date: 2026-09-05
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002_append_only"
down_revision: str | None = "db16edb6d298"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APPEND_ONLY_TABLES = ("audit_log", "evidence_items")


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION tracefall_forbid_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'append-only table %: % is not permitted',
                TG_TABLE_NAME, TG_OP USING ERRCODE = 'check_violation';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    for table in APPEND_ONLY_TABLES:
        op.execute(
            f"""
            CREATE TRIGGER {table}_append_only
            BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION tracefall_forbid_mutation();
            """
        )


def downgrade() -> None:
    for table in APPEND_ONLY_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_append_only ON {table};")
    op.execute("DROP FUNCTION IF EXISTS tracefall_forbid_mutation();")
