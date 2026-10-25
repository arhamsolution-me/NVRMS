"""Stage 1 tests: RBAC permissions, allow/deny, and instant permission toggling."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hub_backend.models.rbac import Permission, Role, RolePermission
from hub_backend.models.tenant import Tenant
from hub_backend.models.user import User
from hub_backend.security.password import hash_password


class TestRBACEnforcement:
    """Tests for RBAC authorization enforcement and immediate toggle effects."""

    @pytest.mark.asyncio
    async def test_superuser_has_unrestricted_access(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Super admin can access all permission-protected endpoints."""
        admin_login = await client.post(
            "/api/v1/auth/login",
            json={"email": "admin@nvrsms.local", "password": "SuperAdmin123!"},
        )
        assert admin_login.status_code == 200
        admin_token = admin_login.json()["access_token"]
        headers = {"Authorization": f"Bearer {admin_token}"}

        # Access roles list (requires roles:read)
        res = await client.get("/api/v1/roles", headers=headers)
        assert res.status_code == 200

        # Access users list (requires users:read)
        res = await client.get("/api/v1/users", headers=headers)
        assert res.status_code == 200

    @pytest.mark.asyncio
    async def test_role_without_permission_receives_403(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """User whose role lacks the required permission is blocked with 403."""
        # Find Viewer role (only has streams:view, locations:read, nvrs:read)
        viewer_role_stmt = select(Role).where(Role.name == "Viewer")
        viewer_role = (await db_session.execute(viewer_role_stmt)).scalar_one()

        tenant_stmt = select(Tenant).limit(1)
        tenant = (await db_session.execute(tenant_stmt)).scalar_one()

        # Create viewer user
        viewer_email = f"viewer_{uuid.uuid4().hex[:8]}@test.local"
        viewer_user = User(
            tenant_id=tenant.id,
            email=viewer_email,
            password_hash=hash_password("Password123!"),
            full_name="Restricted Viewer",
            role_id=viewer_role.id,
            is_active=True,
            is_superuser=False,
        )
        db_session.add(viewer_user)
        await db_session.commit()

        # Login as viewer
        login_res = await client.post(
            "/api/v1/auth/login",
            json={"email": viewer_email, "password": "Password123!"},
        )
        viewer_token = login_res.json()["access_token"]
        viewer_headers = {"Authorization": f"Bearer {viewer_token}"}

        # Attempt to access users list (requires users:read - NOT in viewer role)
        res = await client.get("/api/v1/users", headers=viewer_headers)
        assert res.status_code == 403
        assert "permission denied" in res.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_instant_permission_toggle_effect_on_next_request(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Toggling a permission off immediately blocks the API on the very next request."""
        # 1. Admin login
        admin_login = await client.post(
            "/api/v1/auth/login",
            json={"email": "admin@nvrsms.local", "password": "SuperAdmin123!"},
        )
        admin_token = admin_login.json()["access_token"]
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        # 2. Create custom role with users:read
        tenant = (await db_session.execute(select(Tenant).limit(1))).scalar_one()
        custom_role = Role(
            name=f"Custom Role {uuid.uuid4().hex[:6]}",
            tenant_id=tenant.id,
            is_system=False,
        )
        db_session.add(custom_role)
        await db_session.flush()

        # Grant users:read
        perm_users_read = (
            await db_session.execute(select(Permission).where(Permission.code == "users:read"))
        ).scalar_one()

        rp = RolePermission(
            role_id=custom_role.id,
            permission_id=perm_users_read.id,
            is_granted=True,
        )
        db_session.add(rp)

        # 3. Create user with this role
        user_email = f"operator_{uuid.uuid4().hex[:8]}@test.local"
        test_user = User(
            tenant_id=tenant.id,
            email=user_email,
            password_hash=hash_password("Password123!"),
            full_name="Dynamic Role User",
            role_id=custom_role.id,
            is_active=True,
            is_superuser=False,
        )
        db_session.add(test_user)
        await db_session.commit()

        # 4. User logs in
        login_res = await client.post(
            "/api/v1/auth/login",
            json={"email": user_email, "password": "Password123!"},
        )
        user_token = login_res.json()["access_token"]
        user_headers = {"Authorization": f"Bearer {user_token}"}

        # 5. User accesses /api/v1/users -> SUCCESS (200)
        res_before = await client.get("/api/v1/users", headers=user_headers)
        assert res_before.status_code == 200

        # 6. Admin toggles off 'users:read' for this role
        toggle_res = await client.put(
            f"/api/v1/roles/{custom_role.id}/permissions",
            headers=admin_headers,
            json={"permission_code": "users:read", "is_granted": False},
        )
        assert toggle_res.status_code == 200

        # 7. ON THE VERY NEXT REQUEST: User is blocked with 403 Forbidden!
        res_after = await client.get("/api/v1/users", headers=user_headers)
        assert res_after.status_code == 403
        assert "permission denied" in res_after.json()["detail"].lower()

        # 8. Admin toggles 'users:read' back ON
        toggle_back_res = await client.put(
            f"/api/v1/roles/{custom_role.id}/permissions",
            headers=admin_headers,
            json={"permission_code": "users:read", "is_granted": True},
        )
        assert toggle_back_res.status_code == 200

        # 9. ON THE VERY NEXT REQUEST: User is allowed again (200)
        res_restored = await client.get("/api/v1/users", headers=user_headers)
        assert res_restored.status_code == 200
