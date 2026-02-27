"""Rename observation_tags to observation_scopes in memory_units

Revision ID: a2b3c4d5e6f7
Revises: z1u2v3w4x5y6
Create Date: 2026-02-27

Renames the observation_tags JSONB column to observation_scopes to reflect
the new API design: observation_scopes accepts "per_tag", "combined",
"all_combinations", or a custom list[list[str]].
"""

from collections.abc import Sequence

from alembic import context, op

revision: str = "a2b3c4d5e6f7"
down_revision: str | Sequence[str] | None = "z1u2v3w4x5y6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _get_schema_prefix() -> str:
    """Get schema prefix for table names (required for multi-tenant support)."""
    schema = context.config.get_main_option("target_schema")
    return f'"{schema}".' if schema else ""


def upgrade() -> None:
    schema = _get_schema_prefix()
    op.execute(f"ALTER TABLE {schema}memory_units RENAME COLUMN observation_tags TO observation_scopes")


def downgrade() -> None:
    schema = _get_schema_prefix()
    op.execute(f"ALTER TABLE {schema}memory_units RENAME COLUMN observation_scopes TO observation_tags")
