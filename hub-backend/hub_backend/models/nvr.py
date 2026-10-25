"""NVR (Network Video Recorder) data model."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from hub_backend.models.base import UUIDModel

if TYPE_CHECKING:
    from hub_backend.models.agent import Agent
    from hub_backend.models.camera import Camera
    from hub_backend.models.location import Site
    from hub_backend.models.tenant import Tenant


class NVR(UUIDModel):
    """Network Video Recorder hardware or simulated device."""

    __tablename__ = "nvrs"
    __table_args__ = (
        UniqueConstraint("agent_id", "ip_address", "port", name="uq_nvrs_agent_ip_port"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    site_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("sites.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    brand: Mapped[str] = mapped_column(String(50), nullable=False, default="generic")
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    serial_number: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    mac_address: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)
    port: Mapped[int] = mapped_column(Integer, default=554, nullable=False)
    channel_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="online", nullable=False)

    tenant: Mapped[Tenant] = relationship("Tenant")
    site: Mapped[Site | None] = relationship("Site")
    agent: Mapped[Agent] = relationship("Agent")
    cameras: Mapped[list[Camera]] = relationship(
        "Camera",
        back_populates="nvr",
        cascade="all, delete-orphan",
        order_by="Camera.channel_number",
    )
