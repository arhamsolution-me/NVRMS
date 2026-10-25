"""Create agents and agent_enrolment_tokens tables.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── Agents ────────────────────────────────────────────────
    op.create_table(
        "agents",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("token_hash", sa.String(128), nullable=False, unique=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("version", sa.String(50), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'offline'")),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_ip_address", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_agents_tenant_id", "agents", ["tenant_id"])
    op.create_index("ix_agents_token_hash", "agents", ["token_hash"])

    # ── Agent Enrolment Tokens ────────────────────────────────
    op.create_table(
        "agent_enrolment_tokens",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code_hash", sa.String(128), nullable=False, unique=True),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column(
            "created_by_user_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("is_used", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "agent_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("agents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_agent_enrolment_tokens_tenant_id", "agent_enrolment_tokens", ["tenant_id"])
    op.create_index("ix_agent_enrolment_tokens_code_hash", "agent_enrolment_tokens", ["code_hash"])


def downgrade() -> None:
    op.drop_table("agent_enrolment_tokens")
    op.drop_table("agents")
