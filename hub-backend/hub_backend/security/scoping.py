"""Data scoping and location hierarchy access isolation."""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hub_backend.models.location import Area, City, Province, Site
from hub_backend.models.user import User


async def get_user_accessible_site_ids(
    user: User,
    db: AsyncSession,
) -> set[uuid.UUID] | None:
    """Return the set of accessible Site IDs for a user.

    Returns None if user has full tenant/global access.
    Returns an empty set if user is restricted but has no valid sites.
    """
    if user.is_superuser:
        return None

    # Check scopes
    scopes = user.scopes
    if not scopes:
        # Default: full access within own tenant if no explicit scopes specified
        return None

    # Check for global or tenant-wide scope
    for s in scopes:
        if s.scope_type in ("global", "tenant"):
            return None

    allowed_site_ids: set[uuid.UUID] = set()

    for s in scopes:
        if s.scope_type == "site":
            allowed_site_ids.add(s.scope_id)

        elif s.scope_type == "area":
            stmt = select(Site.id).where(Site.area_id == s.scope_id)
            res = await db.execute(stmt)
            allowed_site_ids.update(res.scalars().all())

        elif s.scope_type == "city":
            stmt = (
                select(Site.id)
                .join(Area, Area.id == Site.area_id)
                .where(Area.city_id == s.scope_id)
            )
            res = await db.execute(stmt)
            allowed_site_ids.update(res.scalars().all())

        elif s.scope_type == "province":
            stmt = (
                select(Site.id)
                .join(Area, Area.id == Site.area_id)
                .join(City, City.id == Area.city_id)
                .where(City.province_id == s.scope_id)
            )
            res = await db.execute(stmt)
            allowed_site_ids.update(res.scalars().all())

    return allowed_site_ids


async def verify_site_access(
    user: User,
    site_id: uuid.UUID,
    db: AsyncSession,
) -> Site:
    """Verify that the user has scope access to a specific site.

    Raises 404/403 if site does not exist or falls outside user scope.
    """
    stmt = (
        select(Site)
        .join(Area, Area.id == Site.area_id)
        .join(City, City.id == Area.city_id)
        .join(Province, Province.id == City.province_id)
        .where(Site.id == site_id)
    )
    res = await db.execute(stmt)
    site = res.scalar_one_or_none()

    if not site:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Site not found",
        )

    # Tenant check
    if not user.is_superuser:
        # Load province to check tenant_id
        stmt_prov = (
            select(Province.tenant_id)
            .join(City, City.province_id == Province.id)
            .join(Area, Area.city_id == City.id)
            .where(Area.id == site.area_id)
        )
        prov_res = await db.execute(stmt_prov)
        tenant_id = prov_res.scalar_one_or_none()
        if tenant_id != user.tenant_id:
            # Conceal existence across tenants
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Site not found",
            )

        accessible_sites = await get_user_accessible_site_ids(user, db)
        if accessible_sites is not None and site.id not in accessible_sites:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Site outside user authorized scope",
            )

    return site
