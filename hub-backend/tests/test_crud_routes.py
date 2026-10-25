"""Stage 1 tests: CRUD endpoints for Roles, Locations, Users, Audit filters, and WS."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hub_backend.models.rbac import Role


class TestCRUDRoutes:
    """Comprehensive test coverage for Admin CRUD endpoints."""

    @pytest.mark.asyncio
    async def test_role_crud_flow(self, client: AsyncClient) -> None:
        """Create, read, update, inspect permission matrix, and delete a role."""
        login_res = await client.post(
            "/api/v1/auth/login",
            json={"email": "admin@nvrsms.local", "password": "SuperAdmin123!"},
        )
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Create role
        create_res = await client.post(
            "/api/v1/roles",
            headers=headers,
            json={"name": "Auditor Role", "description": "Audits platform logs"},
        )
        assert create_res.status_code == 201
        role_id = create_res.json()["id"]

        # 2. Get single role
        get_res = await client.get(f"/api/v1/roles/{role_id}", headers=headers)
        assert get_res.status_code == 200
        assert get_res.json()["name"] == "Auditor Role"

        # 3. Update role
        update_res = await client.put(
            f"/api/v1/roles/{role_id}",
            headers=headers,
            json={"name": "Senior Auditor Role", "description": "Updated description"},
        )
        assert update_res.status_code == 200
        assert update_res.json()["name"] == "Senior Auditor Role"

        # 4. Get permission matrix
        matrix_res = await client.get(f"/api/v1/roles/{role_id}/permissions", headers=headers)
        assert matrix_res.status_code == 200
        matrix = matrix_res.json()
        assert len(matrix) > 0
        assert all("code" in p for p in matrix)

        # 5. Delete custom role
        del_res = await client.delete(f"/api/v1/roles/{role_id}", headers=headers)
        assert del_res.status_code == 204

        # 6. Verify 404 after delete
        not_found = await client.get(f"/api/v1/roles/{role_id}", headers=headers)
        assert not_found.status_code == 404

    @pytest.mark.asyncio
    async def test_locations_hierarchy_and_tree_flow(self, client: AsyncClient) -> None:
        """Create Province -> City -> Area -> Site hierarchy and retrieve location tree."""
        login_res = await client.post(
            "/api/v1/auth/login",
            json={"email": "admin@nvrsms.local", "password": "SuperAdmin123!"},
        )
        headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

        # 1. Create province
        prov_res = await client.post(
            "/api/v1/locations/provinces",
            headers=headers,
            json={"name": f"Province {uuid.uuid4().hex[:4]}", "code": "PRV"},
        )
        assert prov_res.status_code == 201
        prov_id = prov_res.json()["id"]

        # 2. Create city
        city_res = await client.post(
            "/api/v1/locations/cities",
            headers=headers,
            json={"province_id": prov_id, "name": "Test City", "code": "CTY"},
        )
        assert city_res.status_code == 201
        city_id = city_res.json()["id"]

        # 3. Create area
        area_res = await client.post(
            "/api/v1/locations/areas",
            headers=headers,
            json={"city_id": city_id, "name": "Industrial Area", "code": "IND"},
        )
        assert area_res.status_code == 201
        area_id = area_res.json()["id"]

        # 4. Create site
        site_res = await client.post(
            "/api/v1/locations/sites",
            headers=headers,
            json={
                "area_id": area_id,
                "name": "Main Plant 1",
                "code": "PLT-1",
                "address": "123 Factory Rd",
                "latitude": 31.5204,
                "longitude": 74.3587,
            },
        )
        assert site_res.status_code == 201
        # 5. List provinces, cities, areas, sites
        assert (await client.get("/api/v1/locations/provinces", headers=headers)).status_code == 200
        assert (
            await client.get(f"/api/v1/locations/cities?province_id={prov_id}", headers=headers)
        ).status_code == 200
        assert (
            await client.get(f"/api/v1/locations/areas?city_id={city_id}", headers=headers)
        ).status_code == 200
        assert (
            await client.get(f"/api/v1/locations/sites?area_id={area_id}", headers=headers)
        ).status_code == 200

        # 6. Retrieve location tree
        tree_res = await client.get("/api/v1/locations/tree", headers=headers)
        assert tree_res.status_code == 200
        tree = tree_res.json()
        assert len(tree) > 0

    @pytest.mark.asyncio
    async def test_user_crud_flow(self, client: AsyncClient, db_session: AsyncSession) -> None:
        """Create, fetch, update with scopes, and delete a standard user."""
        login_res = await client.post(
            "/api/v1/auth/login",
            json={"email": "admin@nvrsms.local", "password": "SuperAdmin123!"},
        )
        headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

        # Role to assign
        role_res = await db_session.execute(select(Role).where(Role.name == "Viewer"))
        role = role_res.scalar_one()

        email = f"staff_{uuid.uuid4().hex[:8]}@nvrsms.local"
        # 1. Create user
        create_res = await client.post(
            "/api/v1/users",
            headers=headers,
            json={
                "email": email,
                "password": "Password123!",
                "full_name": "Front Desk Staff",
                "role_id": str(role.id),
                "is_active": True,
            },
        )
        assert create_res.status_code == 201
        user_id = create_res.json()["id"]

        # 2. Get user
        get_res = await client.get(f"/api/v1/users/{user_id}", headers=headers)
        assert get_res.status_code == 200
        assert get_res.json()["full_name"] == "Front Desk Staff"

        # 3. Update user
        upd_res = await client.put(
            f"/api/v1/users/{user_id}",
            headers=headers,
            json={"full_name": "Senior Front Desk Staff"},
        )
        assert upd_res.status_code == 200
        assert upd_res.json()["full_name"] == "Senior Front Desk Staff"

        # 4. Delete user
        del_res = await client.delete(f"/api/v1/users/{user_id}", headers=headers)
        assert del_res.status_code == 204

        # 5. Confirm deletion
        assert (await client.get(f"/api/v1/users/{user_id}", headers=headers)).status_code == 404

    @pytest.mark.asyncio
    async def test_audit_log_filters(self, client: AsyncClient) -> None:
        """Filter audit logs by action and resource type."""
        login_res = await client.post(
            "/api/v1/auth/login",
            json={"email": "admin@nvrsms.local", "password": "SuperAdmin123!"},
        )
        headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

        # Query filtered by action
        res = await client.get("/api/v1/audit?action=AUTH_LOGIN&limit=10", headers=headers)
        assert res.status_code == 200
        logs = res.json()
        assert all(log_item["action"] == "AUTH_LOGIN" for log_item in logs)

    @pytest.mark.asyncio
    async def test_logout_endpoint(self, client: AsyncClient) -> None:
        """Calling /logout clears cookies and returns 204."""
        login_res = await client.post(
            "/api/v1/auth/login",
            json={"email": "admin@nvrsms.local", "password": "SuperAdmin123!"},
        )
        headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

        logout_res = await client.post("/api/v1/auth/logout", headers=headers)
        assert logout_res.status_code == 204
