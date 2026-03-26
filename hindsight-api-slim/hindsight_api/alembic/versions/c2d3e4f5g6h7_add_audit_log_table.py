"""Add audit_log table for feature usage tracking.

Merge migration that combines the remaining two heads (b1c2d3e4f5g6 + a2b3c4d5e6f8).

Stores raw request/response as JSONB for expandability without future migrations.
The metadata JSONB column allows adding arbitrary fields in the future.

Revision ID: c2d3e4f5g6h7
Revises: b1c2d3e4f5g6, a2b3c4d5e6f8
Create Date: 2026-03-26
"""

from collections.abc import Sequence

from alembic import context, op

revision: str = "c2d3e4f5g6h7"
down_revision: str | Sequence[str] | None = ("b1c2d3e4f5g6", "a2b3c4d5e6f8")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _get_schema_prefix() -> str:
    """Get schema prefix for table names (required for multi-tenant support)."""
    schema = context.config.get_main_option("target_schema")
    return f'"{schema}".' if schema else ""


def upgrade() -> None:
    schema = _get_schema_prefix()

    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {schema}audit_log (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            action TEXT NOT NULL,
            transport TEXT NOT NULL,
            bank_id TEXT,
            started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            ended_at TIMESTAMPTZ,
            request JSONB,
            response JSONB,
            metadata JSONB DEFAULT '{{}}'::jsonb
        )
        """
    )

    op.execute(
        f"CREATE INDEX IF NOT EXISTS idx_audit_log_action_started ON {schema}audit_log (action, started_at DESC)"
    )
    op.execute(f"CREATE INDEX IF NOT EXISTS idx_audit_log_bank_started ON {schema}audit_log (bank_id, started_at DESC)")
    op.execute(f"CREATE INDEX IF NOT EXISTS idx_audit_log_started ON {schema}audit_log (started_at DESC)")


def downgrade() -> None:
    schema = _get_schema_prefix()

    op.execute(f"DROP INDEX IF EXISTS {schema}idx_audit_log_started")
    op.execute(f"DROP INDEX IF EXISTS {schema}idx_audit_log_bank_started")
    op.execute(f"DROP INDEX IF EXISTS {schema}idx_audit_log_action_started")
    op.execute(f"DROP TABLE IF EXISTS {schema}audit_log")
