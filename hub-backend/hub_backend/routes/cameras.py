"""Camera listing and detail routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hub_backend.db import get_db
from hub_backend.models.camera import Camera
from hub_backend.models.user import User
from hub_backend.schemas.nvr import CameraResponse
from hub_backend.security.rbac import require_permission
from hub_backend.security.scoping import get_user_accessible_site_ids

router = APIRouter(prefix="/api/v1/cameras", tags=["cameras"])


@router.get("", response_model=list[CameraResponse], summary="List cameras")
async def list_cameras(
    nvr_id: uuid.UUID | None = Query(default=None),
    current_user: User = Depends(require_permission("nvrs:read")),
    db: AsyncSession = Depends(get_db),
) -> list[CameraResponse]:
    """List cameras filtered by user location scope and optional NVR ID."""
    stmt = (
        select(Camera)
        .where(Camera.tenant_id == current_user.tenant_id)
        .order_by(Camera.created_at.desc())
    )

    if nvr_id is not None:
        stmt = stmt.where(Camera.nvr_id == nvr_id)

    if not current_user.is_superuser:
        accessible_sites = await get_user_accessible_site_ids(current_user, db)
        if accessible_sites is not None:
            stmt = stmt.where(Camera.site_id.in_(accessible_sites))

    res = await db.execute(stmt)
    cameras = res.scalars().all()
    return [CameraResponse.model_validate(c) for c in cameras]


@router.get("/{camera_id}", response_model=CameraResponse, summary="Get camera details")
async def get_camera(
    camera_id: uuid.UUID,
    current_user: User = Depends(require_permission("nvrs:read")),
    db: AsyncSession = Depends(get_db),
) -> CameraResponse:
    """Get single camera detail with tenant and scope verification."""
    camera = await db.get(Camera, camera_id)
    if not camera or camera.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Camera not found")

    if not current_user.is_superuser:
        accessible_sites = await get_user_accessible_site_ids(current_user, db)
        if accessible_sites is not None and (
            camera.site_id is None or camera.site_id not in accessible_sites
        ):
            raise HTTPException(status_code=404, detail="Camera not found")

    return CameraResponse.model_validate(camera)
