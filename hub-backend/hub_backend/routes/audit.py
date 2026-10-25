"""Audit log inspection endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hub_backend.db import get_db
from hub_backend.models.audit import AuditLog
from hub_backend.models.user import User
from hub_backend.security.rbac import require_permission

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


class AuditLogResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID | None
    user_id: uuid.UUID | None
    action: str
    resource_type: str
    resource_id: str | None
    details: dict[str, Any] | None
    ip_address: str | None
    user_agent: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("", response_model=list[AuditLogResponse], summary="List audit logs")
async def list_audit_logs(
    action: str | None = None,
    resource_type: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(require_permission("audit:read")),
    db: AsyncSession = Depends(get_db),
) -> list[AuditLog]:
    """Retrieve audit logs with optional filtering."""
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc())
    if not current_user.is_superuser:
        stmt = stmt.where(AuditLog.tenant_id == current_user.tenant_id)

    if action:
        stmt = stmt.where(AuditLog.action == action)
    if resource_type:
        stmt = stmt.where(AuditLog.resource_type == resource_type)

    stmt = stmt.limit(limit).offset(offset)
    res = await db.execute(stmt)
    return list(res.scalars().all())
