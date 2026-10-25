"""System seeder: default permissions, system roles, root tenant, and super-admin."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hub_backend.config import get_settings
from hub_backend.logging_config import get_logger
from hub_backend.models.rbac import Permission, Role, RolePermission
from hub_backend.models.tenant import Tenant
from hub_backend.models.user import User
from hub_backend.security.password import hash_password

log = get_logger(__name__)

DEFAULT_PERMISSIONS: list[dict[str, str]] = [
    # Auth
    {
        "code": "auth:login",
        "name": "User Login",
        "module": "auth",
        "description": "Permission to authenticate",
    },
    {
        "code": "auth:totp",
        "name": "Manage TOTP",
        "module": "auth",
        "description": "Permission to configure two-factor authentication",
    },
    # Tenants
    {
        "code": "tenants:read",
        "name": "View Tenants",
        "module": "tenants",
        "description": "View tenant organizations",
    },
    {
        "code": "tenants:write",
        "name": "Manage Tenants",
        "module": "tenants",
        "description": "Create and update tenants",
    },
    # Roles
    {
        "code": "roles:read",
        "name": "View Roles",
        "module": "roles",
        "description": "View roles and permissions",
    },
    {
        "code": "roles:write",
        "name": "Manage Roles",
        "module": "roles",
        "description": "Create and update roles",
    },
    {
        "code": "roles:manage_permissions",
        "name": "Toggle Role Permissions",
        "module": "roles",
        "description": "Modify role permission assignments",
    },
    # Users
    {
        "code": "users:read",
        "name": "View Users",
        "module": "users",
        "description": "View user accounts and profiles",
    },
    {
        "code": "users:write",
        "name": "Manage Users",
        "module": "users",
        "description": "Create, edit and delete users",
    },
    {
        "code": "users:manage_scopes",
        "name": "Manage User Scopes",
        "module": "users",
        "description": "Assign location scopes to users",
    },
    # Locations
    {
        "code": "locations:read",
        "name": "View Locations",
        "module": "locations",
        "description": "View location hierarchy",
    },
    {
        "code": "locations:write",
        "name": "Manage Locations",
        "module": "locations",
        "description": "Create and update provinces, cities, areas, sites",
    },
    # Agents
    {
        "code": "agents:read",
        "name": "View Agents",
        "module": "agents",
        "description": "View agent list and status",
    },
    {
        "code": "agents:write",
        "name": "Manage Agents",
        "module": "agents",
        "description": "Register and update agents",
    },
    {
        "code": "agents:enrol",
        "name": "Enrol Agents",
        "module": "agents",
        "description": "Generate agent enrolment tokens",
    },
    {
        "code": "agents:revoke",
        "name": "Revoke Agents",
        "module": "agents",
        "description": "Revoke and disconnect agents",
    },
    # NVRs
    {
        "code": "nvrs:read",
        "name": "View NVRs",
        "module": "nvrs",
        "description": "View NVR devices and cameras",
    },
    {
        "code": "nvrs:write",
        "name": "Manage NVRs",
        "module": "nvrs",
        "description": "Add, edit, remove NVRs",
    },
    {
        "code": "nvrs:probe",
        "name": "Probe NVRs",
        "module": "nvrs",
        "description": "Probe network devices via agent",
    },
    # Streams
    {
        "code": "streams:view",
        "name": "View Live Streams",
        "module": "streams",
        "description": "Access WebRTC live camera streams",
    },
    {
        "code": "streams:control",
        "name": "Control PTZ Streams",
        "module": "streams",
        "description": "Send PTZ and stream control commands",
    },
    # Audit
    {
        "code": "audit:read",
        "name": "View Audit Logs",
        "module": "audit",
        "description": "Inspect security audit logs",
    },
]


async def seed_initial_data(db: AsyncSession) -> dict[str, Any]:
    """Seed initial permissions, system roles, root tenant, and super-admin user."""
    settings = get_settings()

    # 1. Seed Permissions
    stmt_perms = select(Permission)
    existing_perms_res = await db.execute(stmt_perms)
    existing_perms = {p.code: p for p in existing_perms_res.scalars().all()}

    all_permissions: list[Permission] = []
    for p_data in DEFAULT_PERMISSIONS:
        if p_data["code"] not in existing_perms:
            perm = Permission(
                code=p_data["code"],
                name=p_data["name"],
                module=p_data["module"],
                description=p_data["description"],
            )
            db.add(perm)
            all_permissions.append(perm)
        else:
            all_permissions.append(existing_perms[p_data["code"]])
    await db.flush()

    # 2. Seed Root Tenant
    stmt_tenant = select(Tenant).where(Tenant.slug == "default")
    res_tenant = await db.execute(stmt_tenant)
    root_tenant = res_tenant.scalar_one_or_none()
    if not root_tenant:
        root_tenant = Tenant(
            name="Default Organization",
            slug="default",
            is_active=True,
        )
        db.add(root_tenant)
        await db.flush()

    # 3. Seed System Roles: Super Admin, Operator, Viewer
    stmt_super_role = select(Role).where(Role.name == "Super Admin", Role.is_system.is_(True))
    res_super_role = await db.execute(stmt_super_role)
    super_admin_role = res_super_role.scalar_one_or_none()
    if not super_admin_role:
        super_admin_role = Role(
            name="Super Admin",
            description="System super administrator with full unrestricted access",
            is_system=True,
            tenant_id=root_tenant.id,
        )
        db.add(super_admin_role)
        await db.flush()

    # Ensure all permissions mapped to Super Admin role
    stmt_rp = select(RolePermission.permission_id).where(
        RolePermission.role_id == super_admin_role.id
    )
    res_rp = await db.execute(stmt_rp)
    existing_rp_ids = set(res_rp.scalars().all())

    for perm in all_permissions:
        if perm.id not in existing_rp_ids:
            rp = RolePermission(
                role_id=super_admin_role.id,
                permission_id=perm.id,
                is_granted=True,
            )
            db.add(rp)
    await db.flush()

    # Seed Viewer Role
    stmt_viewer_role = select(Role).where(Role.name == "Viewer", Role.is_system.is_(True))
    res_viewer = await db.execute(stmt_viewer_role)
    viewer_role = res_viewer.scalar_one_or_none()
    if not viewer_role:
        viewer_role = Role(
            name="Viewer",
            description="Read-only camera viewer",
            is_system=True,
            tenant_id=root_tenant.id,
        )
        db.add(viewer_role)
        await db.flush()
        # Assign stream view and read permissions
        viewer_codes = {"streams:view", "locations:read", "nvrs:read"}
        for perm in all_permissions:
            if perm.code in viewer_codes:
                db.add(
                    RolePermission(role_id=viewer_role.id, permission_id=perm.id, is_granted=True)
                )
        await db.flush()

    # 4. Seed Super Admin User
    admin_email = settings.super_admin_email.strip().lower()
    stmt_admin = select(User).where(User.email == admin_email)
    res_admin = await db.execute(stmt_admin)
    admin_user = res_admin.scalar_one_or_none()
    if not admin_user:
        raw_password = settings.super_admin_password.get_secret_value()
        admin_user = User(
            tenant_id=root_tenant.id,
            email=admin_email,
            password_hash=hash_password(raw_password),
            full_name="System Administrator",
            role_id=super_admin_role.id,
            is_active=True,
            is_superuser=True,
        )
        db.add(admin_user)
        await db.flush()
        log.info("super_admin_seeded", email=admin_email)

    await db.commit()
    return {
        "tenant_id": root_tenant.id,
        "super_admin_role_id": super_admin_role.id,
        "admin_user_id": admin_user.id,
    }
