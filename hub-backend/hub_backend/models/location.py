"""Location hierarchy models: Province -> City -> Area -> Site."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from hub_backend.models.base import UUIDModel

if TYPE_CHECKING:
    from hub_backend.models.tenant import Tenant


class Province(UUIDModel):
    """Top-level location hierarchy node."""

    __tablename__ = "provinces"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)

    tenant: Mapped[Tenant] = relationship("Tenant", back_populates="provinces")
    cities: Mapped[list[City]] = relationship(
        "City", back_populates="province", cascade="all, delete-orphan"
    )


class City(UUIDModel):
    """Second-level location hierarchy node."""

    __tablename__ = "cities"

    province_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("provinces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)

    province: Mapped[Province] = relationship("Province", back_populates="cities")
    areas: Mapped[list[Area]] = relationship(
        "Area", back_populates="city", cascade="all, delete-orphan"
    )


class Area(UUIDModel):
    """Third-level location hierarchy node."""

    __tablename__ = "areas"

    city_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("cities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)

    city: Mapped[City] = relationship("City", back_populates="areas")
    sites: Mapped[list[Site]] = relationship(
        "Site", back_populates="area", cascade="all, delete-orphan"
    )


class Site(UUIDModel):
    """Fourth-level location hierarchy node (leaf node where cameras/NVRs reside)."""

    __tablename__ = "sites"

    area_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("areas.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)

    area: Mapped[Area] = relationship("Area", back_populates="sites")
