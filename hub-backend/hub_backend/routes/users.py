"""User management and scope assignment endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from hub_backend.db import get_db
from hub_backend.models.rbac import Role
from hub_backend.models.user import User, UserScope
from hub_backend.schemas.user import UserCreate, UserResponse, UserUpdate
from hub_backend.security.password import hash_password
from hub_backend.security.rbac import require_permission
from hub_backend.services.audit import record_audit_log
from hub_backend.services.auth import check_last_superadmin_protection

router = APIRouter(prefix="/api/v1/users", tags=["users"])


@router.get("", response_model=list[UserResponse], summary="List users")
async def list_users(
    current_user: User = Depends(require_permission("users:read")),
    db: AsyncSession = Depends(get_db),
) -> list[User]:
    stmt = (
        select(User)
        .options(selectinload(User.scopes), selectinload(User.role))
        .order_by(User.created_at.desc())
    )
    if not current_user.is_superuser:
        stmt = stmt.where(User.tenant_id == current_user.tenant_id)
    res = await db.execute(stmt)
    return list(res.scalars().all())


@router.post(
    "", response_model=UserResponse, status_code=status.HTTP_201_CREATED, summary="Create user"
)
async def create_user(
    req: UserCreate,
    current_user: User = Depends(require_permission("users:write")),
    db: AsyncSession = Depends(get_db),
) -> User:
    # Check email duplicate
    email = req.email.strip().lower()
    existing_stmt = select(User).where(User.email == email)
    existing_res = await db.execute(existing_stmt)
    if existing_res.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="User with this email already exists")

    # Validate role
    role = await db.get(Role, req.role_id)
    if not role:
        raise HTTPException(status_code=400, detail="Role not found")

    user = User(
        tenant_id=current_user.tenant_id,
        email=email,
        password_hash=hash_password(req.password),
        full_name=req.full_name,
        role_id=req.role_id,
        is_active=req.is_active,
        is_superuser=False,
    )
    db.add(user)
    await db.flush()

    # Assign scopes
    for sc in req.scopes:
        user_scope = UserScope(
            user_id=user.id,
            scope_type=sc.scope_type,
            scope_id=sc.scope_id,
        )
        db.add(user_scope)

    await db.flush()
    await record_audit_log(
        db=db,
        action="USER_CREATE",
        resource_type="user",
        resource_id=user.id,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        details={"email": email, "role_id": str(req.role_id)},
    )
    await db.commit()

    # Reload with scopes
    stmt = (
        select(User)
        .where(User.id == user.id)
        .options(selectinload(User.scopes), selectinload(User.role))
    )
    res = await db.execute(stmt)
    return res.scalar_one()


@router.get("/{user_id}", response_model=UserResponse, summary="Get user details")
async def get_user(
    user_id: uuid.UUID,
    current_user: User = Depends(require_permission("users:read")),
    db: AsyncSession = Depends(get_db),
) -> User:
    stmt = (
        select(User)
        .where(User.id == user_id)
        .options(selectinload(User.scopes), selectinload(User.role))
    )
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not current_user.is_superuser and user.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.put("/{user_id}", response_model=UserResponse, summary="Update user")
async def update_user(
    user_id: uuid.UUID,
    req: UserUpdate,
    current_user: User = Depends(require_permission("users:write")),
    db: AsyncSession = Depends(get_db),
) -> User:
    stmt = (
        select(User)
        .where(User.id == user_id)
        .options(selectinload(User.scopes), selectinload(User.role))
    )
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not current_user.is_superuser and user.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="User not found")

    # Super-admin protection: cannot deactivate last super-admin
    if req.is_active is False and user.is_active:
        await check_last_superadmin_protection(db, user, demote_or_deactivate=True)

    if req.full_name is not None:
        user.full_name = req.full_name
    if req.role_id is not None:
        role = await db.get(Role, req.role_id)
        if not role:
            raise HTTPException(status_code=400, detail="Role not found")
        user.role_id = req.role_id
    if req.is_active is not None:
        user.is_active = req.is_active
    if req.password:
        user.password_hash = hash_password(req.password)

    # Scopes update if provided
    if req.scopes is not None:
        # Delete existing scopes
        del_stmt = select(UserScope).where(UserScope.user_id == user.id)
        existing_scopes = (await db.execute(del_stmt)).scalars().all()
        for s in existing_scopes:
            await db.delete(s)
        await db.flush()

        for sc in req.scopes:
            db.add(UserScope(user_id=user.id, scope_type=sc.scope_type, scope_id=sc.scope_id))

    await record_audit_log(
        db=db,
        action="USER_UPDATE",
        resource_type="user",
        resource_id=user.id,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
    )
    await db.commit()

    # Re-fetch
    stmt = (
        select(User)
        .where(User.id == user_id)
        .options(selectinload(User.scopes), selectinload(User.role))
    )
    res = await db.execute(stmt)
    return res.scalar_one()


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete user")
async def delete_user(
    user_id: uuid.UUID,
    current_user: User = Depends(require_permission("users:write")),
    db: AsyncSession = Depends(get_db),
) -> None:
    stmt = select(User).where(User.id == user_id)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not current_user.is_superuser and user.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="User not found")

    # Super-admin protection: cannot delete last super-admin
    await check_last_superadmin_protection(db, user, demote_or_deactivate=True)

    await db.delete(user)
    await record_audit_log(
        db=db,
        action="USER_DELETE",
        resource_type="user",
        resource_id=user_id,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
    )
    await db.commit()
