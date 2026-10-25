"""Location hierarchy endpoints: Provinces, Cities, Areas, Sites, and Location Tree."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from hub_backend.db import get_db
from hub_backend.models.location import Area, City, Province, Site
from hub_backend.models.user import User
from hub_backend.schemas.location import (
    AreaCreate,
    AreaResponse,
    CityCreate,
    CityResponse,
    ProvinceCreate,
    ProvinceResponse,
    SiteCreate,
    SiteResponse,
)
from hub_backend.security.rbac import require_permission
from hub_backend.security.scoping import (
    get_user_accessible_site_ids,
    verify_site_access,
)
from hub_backend.services.audit import record_audit_log

router = APIRouter(prefix="/api/v1/locations", tags=["locations"])


# ── Provinces ────────────────────────────────────────────────────────
@router.get("/provinces", response_model=list[ProvinceResponse], summary="List provinces")
async def list_provinces(
    current_user: User = Depends(require_permission("locations:read")),
    db: AsyncSession = Depends(get_db),
) -> list[Province]:
    stmt = select(Province)
    if not current_user.is_superuser:
        stmt = stmt.where(Province.tenant_id == current_user.tenant_id)
    res = await db.execute(stmt)
    return list(res.scalars().all())


@router.post(
    "/provinces",
    response_model=ProvinceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create province",
)
async def create_province(
    req: ProvinceCreate,
    current_user: User = Depends(require_permission("locations:write")),
    db: AsyncSession = Depends(get_db),
) -> Province:
    prov = Province(
        tenant_id=current_user.tenant_id,
        name=req.name,
        code=req.code,
    )
    db.add(prov)
    await db.flush()
    await record_audit_log(
        db=db,
        action="PROVINCE_CREATE",
        resource_type="province",
        resource_id=prov.id,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
    )
    await db.commit()
    return prov


# ── Cities ───────────────────────────────────────────────────────────
@router.get("/cities", response_model=list[CityResponse], summary="List cities")
async def list_cities(
    province_id: uuid.UUID | None = None,
    current_user: User = Depends(require_permission("locations:read")),
    db: AsyncSession = Depends(get_db),
) -> list[City]:
    stmt = select(City).join(Province, Province.id == City.province_id)
    if not current_user.is_superuser:
        stmt = stmt.where(Province.tenant_id == current_user.tenant_id)
    if province_id:
        stmt = stmt.where(City.province_id == province_id)
    res = await db.execute(stmt)
    return list(res.scalars().all())


@router.post(
    "/cities",
    response_model=CityResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create city",
)
async def create_city(
    req: CityCreate,
    current_user: User = Depends(require_permission("locations:write")),
    db: AsyncSession = Depends(get_db),
) -> City:
    # Verify province belongs to tenant
    prov = await db.get(Province, req.province_id)
    if not prov or (not current_user.is_superuser and prov.tenant_id != current_user.tenant_id):
        raise HTTPException(status_code=404, detail="Province not found")

    city = City(province_id=req.province_id, name=req.name, code=req.code)
    db.add(city)
    await db.flush()
    await record_audit_log(
        db=db,
        action="CITY_CREATE",
        resource_type="city",
        resource_id=city.id,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
    )
    await db.commit()
    return city


# ── Areas ────────────────────────────────────────────────────────────
@router.get("/areas", response_model=list[AreaResponse], summary="List areas")
async def list_areas(
    city_id: uuid.UUID | None = None,
    current_user: User = Depends(require_permission("locations:read")),
    db: AsyncSession = Depends(get_db),
) -> list[Area]:
    stmt = (
        select(Area)
        .join(City, City.id == Area.city_id)
        .join(Province, Province.id == City.province_id)
    )
    if not current_user.is_superuser:
        stmt = stmt.where(Province.tenant_id == current_user.tenant_id)
    if city_id:
        stmt = stmt.where(Area.city_id == city_id)
    res = await db.execute(stmt)
    return list(res.scalars().all())


@router.post(
    "/areas",
    response_model=AreaResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create area",
)
async def create_area(
    req: AreaCreate,
    current_user: User = Depends(require_permission("locations:write")),
    db: AsyncSession = Depends(get_db),
) -> Area:
    city = await db.get(City, req.city_id)
    if not city:
        raise HTTPException(status_code=404, detail="City not found")

    area = Area(city_id=req.city_id, name=req.name, code=req.code)
    db.add(area)
    await db.flush()
    await record_audit_log(
        db=db,
        action="AREA_CREATE",
        resource_type="area",
        resource_id=area.id,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
    )
    await db.commit()
    return area


# ── Sites ────────────────────────────────────────────────────────────
@router.get("/sites", response_model=list[SiteResponse], summary="List sites with scope filtering")
async def list_sites(
    area_id: uuid.UUID | None = None,
    current_user: User = Depends(require_permission("locations:read")),
    db: AsyncSession = Depends(get_db),
) -> list[Site]:
    stmt = (
        select(Site)
        .join(Area, Area.id == Site.area_id)
        .join(City, City.id == Area.city_id)
        .join(Province, Province.id == City.province_id)
    )
    if not current_user.is_superuser:
        stmt = stmt.where(Province.tenant_id == current_user.tenant_id)

    if area_id:
        stmt = stmt.where(Site.area_id == area_id)

    # Apply location scope filter
    accessible_sites = await get_user_accessible_site_ids(current_user, db)
    if accessible_sites is not None:
        if not accessible_sites:
            return []
        stmt = stmt.where(Site.id.in_(accessible_sites))

    res = await db.execute(stmt)
    return list(res.scalars().all())


@router.post(
    "/sites",
    response_model=SiteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create site",
)
async def create_site(
    req: SiteCreate,
    current_user: User = Depends(require_permission("locations:write")),
    db: AsyncSession = Depends(get_db),
) -> Site:
    area = await db.get(Area, req.area_id)
    if not area:
        raise HTTPException(status_code=404, detail="Area not found")

    site = Site(
        area_id=req.area_id,
        name=req.name,
        code=req.code,
        address=req.address,
        latitude=req.latitude,
        longitude=req.longitude,
    )
    db.add(site)
    await db.flush()
    await record_audit_log(
        db=db,
        action="SITE_CREATE",
        resource_type="site",
        resource_id=site.id,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
    )
    await db.commit()
    return site


@router.get(
    "/sites/{site_id}",
    response_model=SiteResponse,
    summary="Get single site by ID with scope validation",
)
async def get_site(
    site_id: uuid.UUID,
    current_user: User = Depends(require_permission("locations:read")),
    db: AsyncSession = Depends(get_db),
) -> Site:
    """Fetch site by ID; verifies that site is within user's tenant and location scopes."""
    return await verify_site_access(current_user, site_id, db)


# ── Location Tree ─────────────────────────────────────────────────────
@router.get("/tree", summary="Get hierarchical location tree")
async def get_location_tree(
    current_user: User = Depends(require_permission("locations:read")),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Return the nested tree: Province -> City -> Area -> Site."""
    stmt = select(Province).options(
        selectinload(Province.cities).selectinload(City.areas).selectinload(Area.sites)
    )
    if not current_user.is_superuser:
        stmt = stmt.where(Province.tenant_id == current_user.tenant_id)

    res = await db.execute(stmt)
    provinces = res.scalars().all()

    accessible_sites = await get_user_accessible_site_ids(current_user, db)

    tree: list[dict[str, Any]] = []
    for prov in provinces:
        prov_node: dict[str, Any] = {
            "id": str(prov.id),
            "name": prov.name,
            "code": prov.code,
            "cities": [],
        }
        for city in prov.cities:
            city_node: dict[str, Any] = {
                "id": str(city.id),
                "name": city.name,
                "code": city.code,
                "areas": [],
            }
            for area in city.areas:
                area_node: dict[str, Any] = {
                    "id": str(area.id),
                    "name": area.name,
                    "code": area.code,
                    "sites": [],
                }
                for site in area.sites:
                    if accessible_sites is not None and site.id not in accessible_sites:
                        continue
                    area_node["sites"].append(
                        {
                            "id": str(site.id),
                            "name": site.name,
                            "code": site.code,
                            "address": site.address,
                        }
                    )
                if area_node["sites"] or accessible_sites is None:
                    city_node["areas"].append(area_node)
            if city_node["areas"] or accessible_sites is None:
                prov_node["cities"].append(city_node)
        if prov_node["cities"] or accessible_sites is None:
            tree.append(prov_node)

    return tree
