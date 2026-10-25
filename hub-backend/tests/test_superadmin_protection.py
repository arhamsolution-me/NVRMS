"""Stage 1 tests: Last Super-Admin protection."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


class TestSuperAdminProtection:
    """Tests ensuring the platform cannot be locked out of its last Super Admin."""

    @pytest.mark.asyncio
    async def test_cannot_deactivate_last_super_admin(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Attempting to deactivate the only active super-admin is rejected with 400."""
        # Log in as initial super-admin
        login_res = await client.post(
            "/api/v1/auth/login",
            json={"email": "admin@nvrsms.local", "password": "SuperAdmin123!"},
        )
        assert login_res.status_code == 200
        headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

        # Get own user details
        me_res = await client.get("/api/v1/auth/me", headers=headers)
        admin_id = me_res.json()["id"]

        # Attempt to deactivate self
        deactivate_res = await client.put(
            f"/api/v1/users/{admin_id}",
            headers=headers,
            json={"is_active": False},
        )
        assert deactivate_res.status_code == 400
        assert "last remaining super admin" in deactivate_res.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_cannot_delete_last_super_admin(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Attempting to delete the only active super-admin is rejected with 400."""
        login_res = await client.post(
            "/api/v1/auth/login",
            json={"email": "admin@nvrsms.local", "password": "SuperAdmin123!"},
        )
        headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

        me_res = await client.get("/api/v1/auth/me", headers=headers)
        admin_id = me_res.json()["id"]

        del_res = await client.delete(f"/api/v1/users/{admin_id}", headers=headers)
        assert del_res.status_code == 400
        assert "last remaining super admin" in del_res.json()["detail"].lower()
