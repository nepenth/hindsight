"""Merge two migration heads before audit log table.

Revision ID: b1c2d3e4f5g6
Revises: a3b4c5d6e7f8, c8e5f2a3b4d1
Create Date: 2026-03-26
"""

from collections.abc import Sequence

revision: str = "b1c2d3e4f5g6"
down_revision: str | Sequence[str] | None = ("a3b4c5d6e7f8", "c8e5f2a3b4d1")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
