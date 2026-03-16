"""backsweep_orphan_observations

Delete observation memory_units whose source facts were all deleted before
PR #580 fixed the chunk FK cascade.  Prior to that fix, deleting a document
left chunk-linked memory_units alive (chunk_id SET NULL) and
delete_document() did not call _delete_stale_observations_for_memories, so
derived observations survived with all their source_memory_ids pointing to
rows that no longer exist.

Only observations where *every* source_memory_id is absent from memory_units
are removed — if any source still exists the row is left alone.

Revision ID: g7h8i9j0k1l2
Revises: f6g7h8i9j0k1
Create Date: 2026-03-16
"""

from collections.abc import Sequence

from alembic import context, op

revision: str = "g7h8i9j0k1l2"
down_revision: str | Sequence[str] | None = "f6g7h8i9j0k1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _get_schema_prefix() -> str:
    schema = context.config.get_main_option("target_schema")
    return f'"{schema}".' if schema else ""


def upgrade() -> None:
    schema = _get_schema_prefix()
    mu = f"{schema}memory_units"

    # Delete observation rows that are fully orphaned:
    #   - not anchored to a document or chunk (both columns NULL)
    #   - every entry in source_memory_ids refers to a deleted memory unit
    #     (or the array is empty, which also means no valid source survives)
    op.execute(
        f"""
        DELETE FROM {mu} orphan
        WHERE orphan.fact_type = 'observation'
          AND orphan.document_id IS NULL
          AND orphan.chunk_id IS NULL
          AND NOT EXISTS (
              SELECT 1
              FROM {mu} src
              WHERE src.id = ANY(orphan.source_memory_ids)
                AND src.bank_id = orphan.bank_id
          )
        """
    )


def downgrade() -> None:
    # Deleted rows cannot be restored.
    pass
