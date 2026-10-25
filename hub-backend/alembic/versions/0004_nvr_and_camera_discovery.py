"""Create nvrs and cameras tables.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-26
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── NVRs ──────────────────────────────────────────────────
    op.create_table(
        "nvrs",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("site_id", sa.Uuid(as_uuid=True), sa.ForeignKey("sites.id", ondelete="SET NULL"), nullable=True),
        sa.Column("agent_id", sa.Uuid(as_uuid=True), sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("brand", sa.String(50), nullable=False, server_default=sa.text("'generic'")),
        sa.Column("model", sa.String(100), nullable=True),
        sa.Column("serial_number", sa.String(100), nullable=True),
        sa.Column("mac_address", sa.String(50), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False, server_default=sa.text("554")),
        sa.Column("channel_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'online'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("agent_id", "ip_address", "port", name="uq_nvrs_agent_ip_port"),
    )
    op.create_index("ix_nvrs_tenant_id", "nvrs", ["tenant_id"])
    op.create_index("ix_nvrs_site_id", "nvrs", ["site_id"])
    op.create_index("ix_nvrs_agent_id", "nvrs", ["agent_id"])
    op.create_index("ix_nvrs_serial_number", "nvrs", ["serial_number"])
    op.create_index("ix_nvrs_mac_address", "nvrs", ["mac_address"])

    # ── Cameras ───────────────────────────────────────────────
    op.create_table(
        "cameras",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("site_id", sa.Uuid(as_uuid=True), sa.ForeignKey("sites.id", ondelete="SET NULL"), nullable=True),
        sa.Column("nvr_id", sa.Uuid(as_uuid=True), sa.ForeignKey("nvrs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel_number", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("main_stream_url", sa.String(500), nullable=False),
        sa.Column("sub_stream_url", sa.String(500), nullable=True),
        sa.Column("codec", sa.String(20), nullable=False, server_default=sa.text("'h264'")),
        sa.Column("resolution", sa.String(50), nullable=False, server_default=sa.text("'1920x1080'")),
        sa.Column("fps", sa.Integer(), nullable=False, server_default=sa.text("25")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'online'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("nvr_id", "channel_number", name="uq_cameras_nvr_channel"),
    )
    op.create_index("ix_cameras_tenant_id", "cameras", ["tenant_id"])
    op.create_index("ix_cameras_site_id", "cameras", ["site_id"])
    op.create_index("ix_cameras_nvr_id", "cameras", ["nvr_id"])


def downgrade() -> None:
    op.drop_table("cameras")
    op.drop_table("nvrs")
