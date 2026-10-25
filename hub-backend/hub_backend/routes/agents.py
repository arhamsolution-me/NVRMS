"""Agent administration and enrolment REST endpoints."""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hub_backend.config import get_settings
from hub_backend.db import get_db
from hub_backend.models.agent import Agent, AgentEnrolmentToken
from hub_backend.models.base import ensure_utc
from hub_backend.models.user import User
from hub_backend.schemas.agent import (
    AgentCommandRequest,
    AgentEnrolRequest,
    AgentEnrolResponse,
    AgentResponse,
    EnrolmentTokenCreate,
    EnrolmentTokenResponse,
)
from hub_backend.security.rbac import require_permission
from hub_backend.security.tokens import hash_token
from hub_backend.services.agent_manager import agent_manager
from hub_backend.services.audit import record_audit_log

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])
settings = get_settings()


@router.post(
    "/enrol-token",
    response_model=EnrolmentTokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate single-use agent enrolment code",
)
async def generate_enrolment_token(
    req: EnrolmentTokenCreate,
    current_user: User = Depends(require_permission("agents:enrol")),
    db: AsyncSession = Depends(get_db),
) -> EnrolmentTokenResponse:
    """Generate a single-use 15-minute enrolment code for provisioning a new agent."""
    raw_code = f"ENROL-{secrets.token_hex(4).upper()}-{secrets.token_hex(4).upper()}"
    code_h = hash_token(raw_code)

    now = datetime.now(UTC)
    token = AgentEnrolmentToken(
        tenant_id=current_user.tenant_id,
        code_hash=code_h,
        name=req.name,
        created_by_user_id=current_user.id,
        is_used=False,
        expires_at=now + timedelta(minutes=15),
    )
    db.add(token)
    await db.flush()

    await record_audit_log(
        db=db,
        action="AGENT_ENROL_TOKEN_CREATE",
        resource_type="agent_enrolment_token",
        resource_id=token.id,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        details={"agent_name": req.name},
    )
    await db.commit()

    return EnrolmentTokenResponse(
        id=token.id,
        name=token.name,
        code=raw_code,
        expires_at=token.expires_at,
    )


@router.post(
    "/enrol",
    response_model=AgentEnrolResponse,
    status_code=status.HTTP_200_OK,
    summary="Enrol agent using one-time enrolment code",
)
async def enrol_agent(
    req: AgentEnrolRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> AgentEnrolResponse:
    """Bootstrap endpoint called by edge agents to exchange a single-use code for persistent credentials."""
    code_h = hash_token(req.enrolment_code.strip())
    now = datetime.now(UTC)

    stmt = select(AgentEnrolmentToken).where(AgentEnrolmentToken.code_hash == code_h)
    res = await db.execute(stmt)
    token_rec = res.scalar_one_or_none()

    if not token_rec:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid enrolment code",
        )

    if token_rec.is_used:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Enrolment code has already been used",
        )

    if ensure_utc(token_rec.expires_at) < now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Enrolment code has expired (15 minute validity exceeded)",
        )

    # Generate permanent secret agent token
    raw_agent_token = f"agt_{secrets.token_urlsafe(48)}"
    agent_token_h = hash_token(raw_agent_token)

    agent_name = req.name or token_rec.name
    agent = Agent(
        tenant_id=token_rec.tenant_id,
        name=agent_name,
        token_hash=agent_token_h,
        is_active=True,
        version=req.version,
        status="offline",
        last_ip_address=request.client.host if request.client else None,
    )
    db.add(agent)
    await db.flush()

    # Mark enrolment token as consumed
    token_rec.is_used = True
    token_rec.used_at = now
    token_rec.agent_id = agent.id

    await record_audit_log(
        db=db,
        action="AGENT_ENROLLED",
        resource_type="agent",
        resource_id=agent.id,
        tenant_id=agent.tenant_id,
        details={"name": agent.name, "version": req.version},
        request=request,
    )
    await db.commit()

    return AgentEnrolResponse(
        agent_id=agent.id,
        agent_token=raw_agent_token,
        name=agent.name,
        hub_url=str(request.base_url).rstrip("/"),
    )


@router.get("", response_model=list[AgentResponse], summary="List agents")
async def list_agents(
    current_user: User = Depends(require_permission("agents:read")),
    db: AsyncSession = Depends(get_db),
) -> list[AgentResponse]:
    stmt = select(Agent).order_by(Agent.created_at.desc())
    if not current_user.is_superuser:
        stmt = stmt.where(Agent.tenant_id == current_user.tenant_id)
    res = await db.execute(stmt)
    agents = res.scalars().all()

    return [
        AgentResponse(
            id=a.id,
            tenant_id=a.tenant_id,
            name=a.name,
            is_active=a.is_active,
            version=a.version,
            status="online" if agent_manager.is_online(str(a.id)) else a.status,
            is_online=agent_manager.is_online(str(a.id)),
            last_heartbeat_at=a.last_heartbeat_at,
            last_ip_address=a.last_ip_address,
            created_at=a.created_at,
        )
        for a in agents
    ]


@router.get("/{agent_id}", response_model=AgentResponse, summary="Get agent details")
async def get_agent(
    agent_id: uuid.UUID,
    current_user: User = Depends(require_permission("agents:read")),
    db: AsyncSession = Depends(get_db),
) -> AgentResponse:
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if not current_user.is_superuser and agent.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Agent not found")

    return AgentResponse(
        id=agent.id,
        tenant_id=agent.tenant_id,
        name=agent.name,
        is_active=agent.is_active,
        version=agent.version,
        status="online" if agent_manager.is_online(str(agent.id)) else agent.status,
        is_online=agent_manager.is_online(str(agent.id)),
        last_heartbeat_at=agent.last_heartbeat_at,
        last_ip_address=agent.last_ip_address,
        created_at=agent.created_at,
    )


@router.post("/{agent_id}/revoke", status_code=status.HTTP_200_OK, summary="Revoke agent")
async def revoke_agent(
    agent_id: uuid.UUID,
    current_user: User = Depends(require_permission("agents:revoke")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Revoke an agent: immediately terminates any active WebSocket connection and blocks future access."""
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if not current_user.is_superuser and agent.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Agent not found")

    agent.is_active = False
    agent.status = "revoked"

    # Terminate live WebSocket connection immediately!
    await agent_manager.revoke_agent(str(agent.id))

    await record_audit_log(
        db=db,
        action="AGENT_REVOKE",
        resource_type="agent",
        resource_id=agent.id,
        tenant_id=agent.tenant_id,
        user_id=current_user.id,
    )
    await db.commit()

    return {"status": "ok", "message": f"Agent '{agent.name}' revoked successfully"}


@router.post(
    "/{agent_id}/rotate-credentials",
    status_code=status.HTTP_200_OK,
    summary="Rotate agent credentials",
)
async def rotate_agent_credentials(
    agent_id: uuid.UUID,
    current_user: User = Depends(require_permission("agents:write")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Rotate the authentication token for an agent."""
    agent = await db.get(Agent, agent_id)
    if not agent or not agent.is_active:
        raise HTTPException(status_code=404, detail="Agent not found or inactive")
    if not current_user.is_superuser and agent.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Agent not found")

    new_token = f"agt_{secrets.token_urlsafe(48)}"
    agent.token_hash = hash_token(new_token)

    # Terminate current connection so agent must re-connect with new credentials
    await agent_manager.revoke_agent(str(agent.id))

    await record_audit_log(
        db=db,
        action="AGENT_CREDENTIAL_ROTATED",
        resource_type="agent",
        resource_id=agent.id,
        tenant_id=agent.tenant_id,
        user_id=current_user.id,
    )
    await db.commit()

    return {
        "status": "ok",
        "agent_id": agent.id,
        "new_token": new_token,
    }


@router.post("/{agent_id}/command", summary="Dispatch command to agent")
async def dispatch_command_to_agent(
    agent_id: uuid.UUID,
    req: AgentCommandRequest,
    current_user: User = Depends(require_permission("agents:write")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Send a command to a connected agent and await result."""
    agent = await db.get(Agent, agent_id)
    if not agent or not agent.is_active:
        raise HTTPException(status_code=404, detail="Agent not found or inactive")
    if not current_user.is_superuser and agent.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Agent not found")

    try:
        return await agent_manager.send_command(
            agent_id=str(agent_id),
            command=req.command,
            payload=req.payload,
            timeout_seconds=req.timeout_seconds,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


