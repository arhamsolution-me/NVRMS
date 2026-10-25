"""Initial migration — empty baseline.

This migration creates no tables; it establishes the migration baseline.
All models will be added in subsequent stages.

Revision ID: 0001
Revises: None
Create Date: 2026-10-25
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Enable required PostgreSQL extensions if on PostgreSQL."""
    from alembic import op

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
        op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')


def downgrade() -> None:
    """Remove extensions (only safe in test environments)."""
    pass
