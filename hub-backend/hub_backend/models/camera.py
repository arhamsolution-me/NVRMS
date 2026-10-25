"""Camera / Channel data model."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from hub_backend.models.base import UUIDModel

if TYPE_CHECKING:
    from hub_backend.models.location import Site
    from hub_backend.models.nvr import NVR
    from hub_backend.models.tenant import Tenant


class Camera(UUIDModel):
    """Camera / video channel attached to an NVR."""

    __tablename__ = "cameras"
    __table_args__ = (UniqueConstraint("nvr_id", "channel_number", name="uq_cameras_nvr_channel"),)

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
    nvr_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("nvrs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    channel_number: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    main_stream_url: Mapped[str] = mapped_column(String(500), nullable=False)
    sub_stream_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    codec: Mapped[str] = mapped_column(String(20), default="h264", nullable=False)
    resolution: Mapped[str] = mapped_column(String(50), default="1920x1080", nullable=False)
    fps: Mapped[int] = mapped_column(Integer, default=25, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="online", nullable=False)

    tenant: Mapped[Tenant] = relationship("Tenant")
    site: Mapped[Site | None] = relationship("Site")
    nvr: Mapped[NVR] = relationship("NVR", back_populates="cameras")
