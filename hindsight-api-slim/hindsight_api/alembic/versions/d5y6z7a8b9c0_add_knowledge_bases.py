"""Add knowledge_bases table and kb_id to mental_models

Revision ID: d5y6z7a8b9c0
Revises: c4x5y6z7a8b9
Create Date: 2026-04-17

Adds the knowledge_bases table for organizing mental models into
auto-maintained collections with a shared mission/policy. Each KB
routes tagged observations to its mental models and auto-creates
new MMs when observations don't fit existing ones.

Also adds kb_id FK column to mental_models (nullable for backward
compatibility with standalone MMs).
"""

from collections.abc import Sequence

from alembic import context, op

revision: str = "d5y6z7a8b9c0"
down_revision: str | Sequence[str] | None = "c4x5y6z7a8b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _get_schema_prefix() -> str:
    schema = context.config.get_main_option("target_schema")
    return f'"{schema}".' if schema else ""


def upgrade() -> None:
    schema = _get_schema_prefix()

    # Create knowledge_bases table
    op.execute(f"""
        CREATE TABLE {schema}knowledge_bases (
            id TEXT NOT NULL,
            bank_id TEXT NOT NULL,
            name TEXT NOT NULL DEFAULT '',
            mission TEXT NOT NULL DEFAULT '',
            tags TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
            auto_create BOOLEAN NOT NULL DEFAULT TRUE,
            split_threshold INTEGER NOT NULL DEFAULT 30,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (bank_id, id),
            CONSTRAINT fk_kb_bank FOREIGN KEY (bank_id)
                REFERENCES {schema}banks(bank_id) ON DELETE CASCADE
        )
    """)

    # Add kb_id to mental_models (nullable — standalone MMs have no KB)
    op.execute(f"""
        ALTER TABLE {schema}mental_models
        ADD COLUMN IF NOT EXISTS kb_id TEXT
    """)

    # Index for listing MMs by KB
    op.execute(f"""
        CREATE INDEX IF NOT EXISTS idx_mental_models_kb_id
        ON {schema}mental_models (bank_id, kb_id)
        WHERE kb_id IS NOT NULL
    """)


def downgrade() -> None:
    schema = _get_schema_prefix()

    op.execute(f"DROP INDEX IF EXISTS {schema}idx_mental_models_kb_id")
    op.execute(f"ALTER TABLE {schema}mental_models DROP COLUMN IF EXISTS kb_id")
    op.execute(f"DROP TABLE IF EXISTS {schema}knowledge_bases")
