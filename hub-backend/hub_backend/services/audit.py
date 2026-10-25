"""Audit logging service."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from hub_backend.logging_config import get_logger
from hub_backend.models.audit import AuditLog

log = get_logger(__name__)


async def record_audit_log(
    db: AsyncSession,
    action: str,
    resource_type: str,
    resource_id: str | uuid.UUID | None = None,
    tenant_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    details: dict[str, Any] | None = None,
    request: Request | None = None,
) -> AuditLog:
    """Record an immutable audit log entry."""
    ip_address: str | None = None
    user_agent: str | None = None

    if request is not None:
        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")

    res_id_str = str(resource_id) if resource_id is not None else None

    entry = AuditLog(
        tenant_id=tenant_id,
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=res_id_str,
        details=details,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(entry)
    await db.flush()

    log.info(
        "audit_event",
        action=action,
        resource_type=resource_type,
        resource_id=res_id_str,
        user_id=str(user_id) if user_id else None,
        tenant_id=str(tenant_id) if tenant_id else None,
    )

    return entry
