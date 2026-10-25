"""Audit logging service with cryptographic hash chaining for tamper-evident immutability."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hub_backend.logging_config import get_logger
from hub_backend.models.audit import AuditLog

log = get_logger(__name__)

GENESIS_PREV_HASH = "0" * 64

_last_audit_ts: float = 0.0


def monotonic_audit_now() -> datetime:
    """Generate strictly monotonically increasing UTC timestamps to ensure deterministic ordering."""
    global _last_audit_ts
    now_ts = time.time()
    if now_ts <= _last_audit_ts:
        now_ts = _last_audit_ts + 0.0001
    _last_audit_ts = now_ts
    return datetime.fromtimestamp(now_ts, tz=UTC)


def compute_entry_hash(
    prev_hash: str,
    action: str,
    resource_type: str,
    resource_id: str | None,
    user_id: str | None,
    tenant_id: str | None,
    details: dict[str, Any] | None,
) -> str:
    """Compute SHA-256 hash chaining to prev_hash."""
    hasher = hashlib.sha256()
    hasher.update(prev_hash.encode("utf-8"))
    hasher.update(action.encode("utf-8"))
    hasher.update(resource_type.encode("utf-8"))
    hasher.update((resource_id or "").encode("utf-8"))
    hasher.update((user_id or "").encode("utf-8"))
    hasher.update((tenant_id or "").encode("utf-8"))
    if details:
        hasher.update(json.dumps(details, sort_keys=True).encode("utf-8"))
    return hasher.hexdigest()


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
    """Record an immutable, hash-chained audit log entry."""
    ip_address: str | None = None
    user_agent: str | None = None

    if request is not None:
        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")

    res_id_str = str(resource_id) if resource_id is not None else None
    user_id_str = str(user_id) if user_id is not None else None
    tenant_id_str = str(tenant_id) if tenant_id is not None else None

    # Retrieve latest entry with record_hash to obtain previous hash
    stmt = (
        select(AuditLog)
        .where(AuditLog.record_hash.is_not(None))
        .order_by(AuditLog.created_at.desc())
        .limit(1)
    )
    res = await db.execute(stmt)
    latest = res.scalar_one_or_none()

    prev_hash = latest.record_hash if (latest and latest.record_hash) else GENESIS_PREV_HASH
    rec_hash = compute_entry_hash(
        prev_hash=prev_hash,
        action=action,
        resource_type=resource_type,
        resource_id=res_id_str,
        user_id=user_id_str,
        tenant_id=tenant_id_str,
        details=details,
    )

    created_timestamp = monotonic_audit_now()
    entry = AuditLog(
        tenant_id=tenant_id,
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=res_id_str,
        details=details,
        ip_address=ip_address,
        user_agent=user_agent,
        prev_hash=prev_hash,
        record_hash=rec_hash,
        created_at=created_timestamp,
        updated_at=created_timestamp,
    )
    db.add(entry)
    await db.flush()

    log.info(
        "audit_event",
        action=action,
        resource_type=resource_type,
        resource_id=res_id_str,
        user_id=user_id_str,
        tenant_id=tenant_id_str,
        record_hash=rec_hash,
    )

    return entry


async def verify_audit_log_chain(db: AsyncSession) -> tuple[bool, int, str | None]:
    """Verify cryptographic integrity of the entire audit log chain.

    Returns:
        (is_valid, record_count, error_message_if_tampered)
    """
    stmt = (
        select(AuditLog)
        .where(AuditLog.record_hash.is_not(None))
        .order_by(AuditLog.created_at.asc())
    )
    res = await db.execute(stmt)
    records = list(res.scalars().all())

    expected_prev = GENESIS_PREV_HASH

    for idx, r in enumerate(records):
        if r.prev_hash != expected_prev:
            return (
                False,
                idx,
                f"Broken hash chain at row {idx} (id={r.id}): expected prev_hash {expected_prev}, got {r.prev_hash}",
            )

        calculated_hash = compute_entry_hash(
            prev_hash=r.prev_hash,
            action=r.action,
            resource_type=r.resource_type,
            resource_id=r.resource_id,
            user_id=str(r.user_id) if r.user_id else None,
            tenant_id=str(r.tenant_id) if r.tenant_id else None,
            details=r.details,
        )

        if r.record_hash != calculated_hash:
            return (
                False,
                idx,
                f"Tampered record content at row {idx} (id={r.id}): calculated {calculated_hash}, found {r.record_hash}",
            )

        expected_prev = r.record_hash

    return True, len(records), None
