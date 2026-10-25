"""Media streaming control, playback tokens, and MediaMTX authentication webhooks."""

from __future__ import annotations

import urllib.parse
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hub_backend.db import get_db
from hub_backend.models.agent import Agent
from hub_backend.models.camera import Camera
from hub_backend.models.nvr import NVR
from hub_backend.models.user import User
from hub_backend.security.rbac import require_permission
from hub_backend.security.scoping import verify_site_access
from hub_backend.security.stream_tokens import (
    STREAM_TOKEN_LIFETIME_SECONDS,
    create_stream_token,
    verify_stream_token,
)
from hub_backend.security.tokens import hash_token
from hub_backend.services.audit import record_audit_log
from hub_backend.services.stream_manager import stream_manager

router = APIRouter(prefix="/api/v1/streams", tags=["streams"])


class StreamTokenRequest(BaseModel):
    stream_type: str = Field(default="sub", description="'main' for fullscreen, 'sub' for grid")


class StreamTokenResponse(BaseModel):
    token: str
    stream_id: str
    stream_type: str
    target_path: str
    viewer_id: str
    expires_in_seconds: int = STREAM_TOKEN_LIFETIME_SECONDS


class StreamStopRequest(BaseModel):
    viewer_id: str
    stream_type: str = "sub"


class MediaMTXAuthRequest(BaseModel):
    action: str = Field(..., description="'publish' or 'read'")
    path: str
    query: str | None = None
    user: str | None = None
    password: str | None = None
    ip: str | None = None


@router.post(
    "/{camera_id}/token", response_model=StreamTokenResponse, summary="Request playback token"
)
async def get_stream_token(
    camera_id: uuid.UUID,
    req: StreamTokenRequest,
    current_user: User = Depends(require_permission("streams:view")),
    db: AsyncSession = Depends(get_db),
) -> StreamTokenResponse:
    """Generate user-bound stream token and ensure agent starts on-demand video worker."""
    camera = await db.get(Camera, camera_id)
    if not camera or camera.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Camera not found")

    if not camera.is_active:
        raise HTTPException(status_code=400, detail="Camera is disabled")

    # Scope check
    if not current_user.is_superuser and camera.site_id:
        await verify_site_access(current_user, camera.site_id, db)

    # Resolve NVR
    nvr = await db.get(NVR, camera.nvr_id)
    if not nvr:
        raise HTTPException(status_code=404, detail="Camera NVR not found")

    viewer_id = str(uuid.uuid4())
    stream_type = req.stream_type.lower()
    if stream_type not in ("main", "sub"):
        stream_type = "sub"

    # Request stream via StreamManager (handles 1:N fan-out & on-demand start)
    session, _ = await stream_manager.request_stream(
        camera=camera,
        nvr=nvr,
        stream_type=stream_type,
        viewer_id=viewer_id,
    )

    token = create_stream_token(
        user_id=current_user.id,
        camera_id=camera.id,
        tenant_id=current_user.tenant_id,
        stream_type=stream_type,
    )

    await record_audit_log(
        db=db,
        action="STREAM_START",
        resource_type="camera",
        resource_id=camera.id,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        details={"stream_type": stream_type, "stream_id": session.stream_id},
    )
    await db.commit()

    return StreamTokenResponse(
        token=token,
        stream_id=session.stream_id,
        stream_type=stream_type,
        target_path=session.target_path,
        viewer_id=viewer_id,
        expires_in_seconds=STREAM_TOKEN_LIFETIME_SECONDS,
    )


@router.post("/{camera_id}/heartbeat", summary="Keep stream viewer session alive")
async def stream_heartbeat(
    camera_id: uuid.UUID,
    req: StreamStopRequest,
    current_user: User = Depends(require_permission("streams:view")),
) -> dict[str, str]:
    """Client periodic ping to keep viewer session active and prevent idle timeout."""
    stream_key = stream_manager.get_stream_key(camera_id, req.stream_type)
    session = stream_manager.active_streams.get(stream_key)
    if session and req.viewer_id in session.viewers:
        return {"status": "ok"}
    return {"status": "reconnect_required"}


@router.post("/{camera_id}/stop", summary="Stop viewer session")
async def stop_stream_session(
    camera_id: uuid.UUID,
    req: StreamStopRequest,
    current_user: User = Depends(require_permission("streams:view")),
) -> dict[str, str]:
    """Client unmounts player or navigates away; triggers grace period for stream shutdown."""
    await stream_manager.leave_stream(
        camera_id=camera_id,
        stream_type=req.stream_type,
        viewer_id=req.viewer_id,
    )
    return {"status": "ok"}


@router.post("/auth", status_code=status.HTTP_200_OK, summary="MediaMTX external auth webhook")
async def mediamtx_auth_webhook(
    req: MediaMTXAuthRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """External webhook invoked by MediaMTX to authenticate publishing agents and reading viewers.

    Returns HTTP 200 on success, or raises 403 on invalid credentials/token.
    """
    clean_path = req.path.strip("/")

    if req.action == "publish":
        # Publishing agent authentication:
        # Agent sends password in basic auth or bearer token in query
        agent_token = req.password or ""
        if not agent_token and req.query:
            parsed = urllib.parse.parse_qs(req.query)
            agent_token = parsed.get("token", [""])[0]

        if not agent_token:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing agent token")

        # Verify agent token against DB
        h_token = hash_token(agent_token)
        stmt = select(Agent).where(Agent.token_hash == h_token, Agent.is_active.is_(True))
        res = await db.execute(stmt)
        agent = res.scalar_one_or_none()
        if not agent:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Invalid agent credentials"
            )

        return {"status": "ok"}

    if req.action == "read":
        # Viewer reading stream:
        # Client passes stream token in query string: ?token=<jwt>
        stream_token = ""
        if req.query:
            parsed = urllib.parse.parse_qs(req.query)
            stream_token = parsed.get("token", [""])[0]
        if not stream_token and req.password:
            stream_token = req.password

        if not stream_token:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Missing stream token"
            )

        try:
            payload = verify_stream_token(stream_token)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

        # Verify that token matches the requested path:
        # path is expected to be "live/{camera_id}_{stream_type}"
        expected_suffix = f"{payload['camera_id']}_{payload['stream_type']}"
        if expected_suffix not in clean_path:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Stream token does not match requested camera stream",
            )

        return {"status": "ok"}

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported action")


@router.get("/active", summary="List active stream sessions")
async def list_active_streams(
    current_user: User = Depends(require_permission("streams:view")),
) -> list[dict[str, Any]]:
    """Inspect live streaming sessions across the platform."""
    return [
        {
            "stream_id": s.stream_id,
            "camera_id": str(s.camera_id),
            "agent_id": str(s.agent_id),
            "stream_type": s.stream_type,
            "target_path": s.target_path,
            "viewer_count": s.viewer_count,
            "started_at": s.started_at.isoformat(),
        }
        for s in stream_manager.active_streams.values()
        if current_user.is_superuser or s.tenant_id == current_user.tenant_id
    ]
