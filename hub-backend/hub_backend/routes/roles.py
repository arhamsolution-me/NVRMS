"""Roles and Permission matrix management endpoints."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hub_backend.db import get_db
from hub_backend.models.rbac import Permission, Role, RolePermission
from hub_backend.models.user import User
from hub_backend.schemas.rbac import (
    RoleCreate,
    RolePermissionItem,
    RolePermissionToggleRequest,
    RoleResponse,
    RoleUpdate,
)
from hub_backend.security.rbac import (
    invalidate_role_cache,
    require_permission,
)
from hub_backend.services.audit import record_audit_log

router = APIRouter(prefix="/api/v1/roles", tags=["roles"])


@router.get("", response_model=list[RoleResponse], summary="List roles")
async def list_roles(
    current_user: User = Depends(require_permission("roles:read")),
    db: AsyncSession = Depends(get_db),
) -> list[Role]:
    """List all roles in current tenant or system roles."""
    stmt = select(Role)
    if not current_user.is_superuser:
        stmt = stmt.where((Role.tenant_id == current_user.tenant_id) | (Role.tenant_id.is_(None)))
    res = await db.execute(stmt)
    return list(res.scalars().all())


@router.post(
    "", response_model=RoleResponse, status_code=status.HTTP_201_CREATED, summary="Create role"
)
async def create_role(
    req: RoleCreate,
    current_user: User = Depends(require_permission("roles:write")),
    db: AsyncSession = Depends(get_db),
) -> Role:
    """Create a new custom role."""
    role = Role(
        name=req.name,
        description=req.description,
        tenant_id=current_user.tenant_id,
        is_system=False,
    )
    db.add(role)
    await db.flush()

    await record_audit_log(
        db=db,
        action="ROLE_CREATE",
        resource_type="role",
        resource_id=role.id,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        details={"name": role.name},
    )
    await db.commit()
    return role


@router.get("/{role_id}", response_model=RoleResponse, summary="Get role details")
async def get_role(
    role_id: uuid.UUID,
    current_user: User = Depends(require_permission("roles:read")),
    db: AsyncSession = Depends(get_db),
) -> Role:
    stmt = select(Role).where(Role.id == role_id)
    res = await db.execute(stmt)
    role = res.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    if (
        not current_user.is_superuser
        and role.tenant_id
        and role.tenant_id != current_user.tenant_id
    ):
        raise HTTPException(status_code=404, detail="Role not found")
    return role


@router.put("/{role_id}", response_model=RoleResponse, summary="Update role")
async def update_role(
    role_id: uuid.UUID,
    req: RoleUpdate,
    current_user: User = Depends(require_permission("roles:write")),
    db: AsyncSession = Depends(get_db),
) -> Role:
    stmt = select(Role).where(Role.id == role_id)
    res = await db.execute(stmt)
    role = res.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    if role.is_system:
        raise HTTPException(status_code=400, detail="Cannot modify system roles")

    if req.name is not None:
        role.name = req.name
    if req.description is not None:
        role.description = req.description

    await record_audit_log(
        db=db,
        action="ROLE_UPDATE",
        resource_type="role",
        resource_id=role.id,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
    )
    await db.commit()
    return role


@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete role")
async def delete_role(
    role_id: uuid.UUID,
    current_user: User = Depends(require_permission("roles:write")),
    db: AsyncSession = Depends(get_db),
) -> None:
    stmt = select(Role).where(Role.id == role_id)
    res = await db.execute(stmt)
    role = res.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    if role.is_system:
        raise HTTPException(status_code=400, detail="Cannot delete system roles")

    await db.delete(role)
    await record_audit_log(
        db=db,
        action="ROLE_DELETE",
        resource_type="role",
        resource_id=role_id,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
    )
    await db.commit()


@router.get(
    "/{role_id}/permissions",
    response_model=list[RolePermissionItem],
    summary="Get role permission matrix",
)
async def get_role_permissions_matrix(
    role_id: uuid.UUID,
    current_user: User = Depends(require_permission("roles:read")),
    db: AsyncSession = Depends(get_db),
) -> list[RolePermissionItem]:
    """Return all permissions with their granted status for the given role."""
    # Get all permissions
    perms_res = await db.execute(select(Permission).order_by(Permission.module, Permission.name))
    all_perms = perms_res.scalars().all()

    # Get role's existing assignments
    rp_res = await db.execute(select(RolePermission).where(RolePermission.role_id == role_id))
    rp_map = {rp.permission_id: rp.is_granted for rp in rp_res.scalars().all()}

    items: list[RolePermissionItem] = []
    for p in all_perms:
        items.append(
            RolePermissionItem(
                permission_id=p.id,
                code=p.code,
                name=p.name,
                module=p.module,
                is_granted=rp_map.get(p.id, False),
            )
        )
    return items


@router.put(
    "/{role_id}/permissions", status_code=status.HTTP_200_OK, summary="Toggle role permission"
)
async def toggle_role_permission(
    role_id: uuid.UUID,
    req: RolePermissionToggleRequest,
    current_user: User = Depends(require_permission("roles:manage_permissions")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Toggle a permission on/off for a role with immediate cache invalidation and WS broadcast."""
    # Find permission
    perm_stmt = select(Permission).where(Permission.code == req.permission_code)
    perm_res = await db.execute(perm_stmt)
    perm = perm_res.scalar_one_or_none()
    if not perm:
        raise HTTPException(status_code=404, detail=f"Permission '{req.permission_code}' not found")

    # Find or create RolePermission record
    rp_stmt = select(RolePermission).where(
        RolePermission.role_id == role_id,
        RolePermission.permission_id == perm.id,
    )
    rp_res = await db.execute(rp_stmt)
    rp = rp_res.scalar_one_or_none()

    if not rp:
        rp = RolePermission(
            role_id=role_id,
            permission_id=perm.id,
            is_granted=req.is_granted,
        )
        db.add(rp)
    else:
        rp.is_granted = req.is_granted

    await db.flush()

    # Invalidate cache immediately!
    await invalidate_role_cache(role_id)

    await record_audit_log(
        db=db,
        action="PERMISSION_TOGGLE",
        resource_type="role_permission",
        resource_id=role_id,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        details={
            "role_id": str(role_id),
            "permission_code": req.permission_code,
            "is_granted": req.is_granted,
        },
    )
    await db.commit()

    return {
        "status": "ok",
        "role_id": role_id,
        "permission_code": req.permission_code,
        "is_granted": req.is_granted,
    }
