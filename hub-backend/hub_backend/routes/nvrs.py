"""NVR discovery, onboarding, and management routes."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from hub_backend.db import get_db
from hub_backend.models.agent import Agent
from hub_backend.models.camera import Camera
from hub_backend.models.nvr import NVR
from hub_backend.models.user import User
from hub_backend.schemas.nvr import (
    CameraResponse,
    NVRCreateRequest,
    NVRProbeRequest,
    NVRProbeResponse,
    NVRResponse,
    NVRUpdateRequest,
)
from hub_backend.security.rbac import require_permission
from hub_backend.security.scoping import (
    get_user_accessible_site_ids,
    verify_site_access,
)
from hub_backend.services.agent_manager import agent_manager
from hub_backend.services.audit import record_audit_log

router = APIRouter(prefix="/api/v1/nvrs", tags=["nvrs"])


@router.post("/probe", response_model=NVRProbeResponse, summary="Probe NVR by IP via agent")
async def probe_nvr(
    req: NVRProbeRequest,
    current_user: User = Depends(require_permission("nvrs:probe")),
    db: AsyncSession = Depends(get_db),
) -> NVRProbeResponse:
    """Instruct the edge agent to probe an NVR by IP, test streams, and enumerate channels."""
    agent = await db.get(Agent, req.agent_id)
    if not agent or not agent.is_active:
        raise HTTPException(status_code=404, detail="Agent not found or inactive")
    if not current_user.is_superuser and agent.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Agent not found")

    if not agent_manager.is_online(str(agent.id)):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Agent '{agent.name}' is currently offline",
        )

    # Dispatch probe_nvr command to agent
    try:
        raw_result = await agent_manager.send_command(
            agent_id=str(agent.id),
            command="probe_nvr",
            payload={
                "ip": req.ip,
                "port": req.port,
                "username": req.username,
                "password": req.password,
                "brand": req.brand,
            },
            timeout_seconds=25,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Probe command failed: {exc}",
        ) from exc

    probe_data: dict[str, Any] = raw_result.get("result", {})
    if raw_result.get("status") == "error":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=raw_result.get("error", "NVR probe failed"),
        )

    await record_audit_log(
        db=db,
        action="NVR_PROBED",
        resource_type="nvr",
        resource_id=agent.id,
        tenant_id=agent.tenant_id,
        user_id=current_user.id,
        details={"ip": req.ip, "agent_id": str(agent.id), "brand": probe_data.get("brand")},
    )
    await db.commit()

    return NVRProbeResponse(
        status=probe_data.get("status", "success"),
        brand=probe_data.get("brand", req.brand),
        model=probe_data.get("model"),
        serial_number=probe_data.get("serial_number"),
        mac_address=probe_data.get("mac_address"),
        ip=req.ip,
        port=req.port,
        channel_count=probe_data.get("channel_count", len(probe_data.get("channels", []))),
        channels=probe_data.get("channels", []),
        diagnostics=probe_data.get("diagnostics", {}),
    )


@router.post("", response_model=NVRResponse, status_code=status.HTTP_201_CREATED, summary="Add NVR")
async def create_nvr(
    req: NVRCreateRequest,
    current_user: User = Depends(require_permission("nvrs:write")),
    db: AsyncSession = Depends(get_db),
) -> NVRResponse:
    """Create NVR entity and its cameras. Passwords are stored encrypted only on the agent."""
    agent = await db.get(Agent, req.agent_id)
    if not agent or not agent.is_active:
        raise HTTPException(status_code=404, detail="Agent not found or inactive")
    if not current_user.is_superuser and agent.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Validate site if provided
    if req.site_id:
        await verify_site_access(current_user, req.site_id, db)

    # Check uniqueness on (agent_id, ip_address, port)
    dup_stmt = select(NVR).where(
        NVR.agent_id == agent.id,
        NVR.ip_address == req.ip_address,
        NVR.port == req.port,
    )
    dup_res = await db.execute(dup_stmt)
    if dup_res.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An NVR with IP {req.ip_address}:{req.port} is already registered on this agent",
        )

    # Create NVR entity
    nvr = NVR(
        tenant_id=current_user.tenant_id,
        site_id=req.site_id,
        agent_id=agent.id,
        name=req.name,
        brand=req.brand,
        model=req.model,
        serial_number=req.serial_number,
        mac_address=req.mac_address,
        ip_address=req.ip_address,
        port=req.port,
        channel_count=len(req.channels),
        status="online",
    )
    db.add(nvr)
    await db.flush()

    # Create Camera entities
    created_cameras: list[Camera] = []
    for ch in req.channels:
        cam = Camera(
            tenant_id=current_user.tenant_id,
            site_id=req.site_id,
            nvr_id=nvr.id,
            channel_number=ch.channel_number,
            name=ch.name or f"Channel {ch.channel_number}",
            main_stream_url=ch.main_stream_url,
            sub_stream_url=ch.sub_stream_url,
            codec=ch.codec or "h264",
            resolution=ch.resolution or "1920x1080",
            fps=ch.fps or 25,
            is_active=True,
            status=ch.status or "online",
        )
        db.add(cam)
        created_cameras.append(cam)

    await db.flush()

    await record_audit_log(
        db=db,
        action="NVR_CREATE",
        resource_type="nvr",
        resource_id=nvr.id,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        details={"name": nvr.name, "ip": nvr.ip_address, "channels": len(created_cameras)},
    )
    await db.commit()

    return NVRResponse(
        id=nvr.id,
        tenant_id=nvr.tenant_id,
        site_id=nvr.site_id,
        agent_id=nvr.agent_id,
        name=nvr.name,
        brand=nvr.brand,
        model=nvr.model,
        serial_number=nvr.serial_number,
        mac_address=nvr.mac_address,
        ip_address=nvr.ip_address,
        port=nvr.port,
        channel_count=nvr.channel_count,
        status=nvr.status,
        created_at=nvr.created_at,
        cameras=[CameraResponse.model_validate(c) for c in created_cameras],
    )


@router.get("", response_model=list[NVRResponse], summary="List NVRs")
async def list_nvrs(
    current_user: User = Depends(require_permission("nvrs:read")),
    db: AsyncSession = Depends(get_db),
) -> list[NVRResponse]:
    """List NVRs filtered by tenant and user location scopes."""
    stmt = (
        select(NVR)
        .options(selectinload(NVR.cameras))
        .where(NVR.tenant_id == current_user.tenant_id)
        .order_by(NVR.created_at.desc())
    )

    if not current_user.is_superuser:
        accessible_sites = await get_user_accessible_site_ids(current_user, db)
        if accessible_sites is not None:
            stmt = stmt.where(NVR.site_id.in_(accessible_sites))

    res = await db.execute(stmt)
    nvrs = res.scalars().all()
    return [NVRResponse.model_validate(n) for n in nvrs]


@router.get("/{nvr_id}", response_model=NVRResponse, summary="Get NVR details")
async def get_nvr(
    nvr_id: uuid.UUID,
    current_user: User = Depends(require_permission("nvrs:read")),
    db: AsyncSession = Depends(get_db),
) -> NVRResponse:
    """Get NVR detail and its attached cameras."""
    stmt = (
        select(NVR)
        .options(selectinload(NVR.cameras))
        .where(NVR.id == nvr_id, NVR.tenant_id == current_user.tenant_id)
    )
    res = await db.execute(stmt)
    nvr = res.scalar_one_or_none()
    if not nvr:
        raise HTTPException(status_code=404, detail="NVR not found")

    if not current_user.is_superuser:
        accessible_sites = await get_user_accessible_site_ids(current_user, db)
        if accessible_sites is not None and (
            nvr.site_id is None or nvr.site_id not in accessible_sites
        ):
            raise HTTPException(status_code=404, detail="NVR not found")

    return NVRResponse.model_validate(nvr)


@router.patch("/{nvr_id}", response_model=NVRResponse, summary="Update NVR")
async def update_nvr(
    nvr_id: uuid.UUID,
    req: NVRUpdateRequest,
    current_user: User = Depends(require_permission("nvrs:write")),
    db: AsyncSession = Depends(get_db),
) -> NVRResponse:
    """Update NVR name, site, or status."""
    stmt = (
        select(NVR)
        .options(selectinload(NVR.cameras))
        .where(NVR.id == nvr_id, NVR.tenant_id == current_user.tenant_id)
    )
    res = await db.execute(stmt)
    nvr = res.scalar_one_or_none()
    if not nvr:
        raise HTTPException(status_code=404, detail="NVR not found")

    if req.name is not None:
        nvr.name = req.name
    if req.site_id is not None:
        nvr.site_id = req.site_id
    if req.status is not None:
        nvr.status = req.status

    await record_audit_log(
        db=db,
        action="NVR_UPDATE",
        resource_type="nvr",
        resource_id=nvr.id,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
    )
    await db.commit()
    return NVRResponse.model_validate(nvr)


@router.delete("/{nvr_id}", summary="Delete NVR")
async def delete_nvr(
    nvr_id: uuid.UUID,
    current_user: User = Depends(require_permission("nvrs:write")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Delete NVR and cascade delete its cameras."""
    nvr = await db.get(NVR, nvr_id)
    if not nvr or nvr.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="NVR not found")

    await db.delete(nvr)
    await record_audit_log(
        db=db,
        action="NVR_DELETE",
        resource_type="nvr",
        resource_id=nvr_id,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
    )
    await db.commit()
    return {"status": "ok", "message": "NVR and associated cameras deleted"}
