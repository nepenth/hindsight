"""
Oracle 23ai database migrations.

Stub module — full implementation is part of Phase 2 (Oracle integration).
Oracle uses idempotent DDL (CREATE TABLE IF NOT EXISTS, etc.) rather than
Alembic's sequential migration approach.
"""

import logging

logger = logging.getLogger(__name__)


def run_oracle_migrations(dsn: str, *, schema: str | None = None) -> None:
    """Run Oracle schema migrations.

    Args:
        dsn: Oracle connection string
        schema: Target schema (Oracle user). None uses the connecting user's default.
    """
    logger.info("Oracle migrations: stub — no-op (full implementation pending)")
