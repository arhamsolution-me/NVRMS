"""Add prev_hash and record_hash to audit_logs for cryptographic immutability.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("audit_logs") as batch_op:
        batch_op.add_column(sa.Column("prev_hash", sa.String(64), nullable=True))
        batch_op.add_column(sa.Column("record_hash", sa.String(64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("audit_logs") as batch_op:
        batch_op.drop_column("record_hash")
        batch_op.drop_column("prev_hash")
