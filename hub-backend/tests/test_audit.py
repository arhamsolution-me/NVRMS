"""Stage 1 tests: Audit log recording and querying."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


class TestAuditLogging:
    """Tests verifying that security and administrative actions generate audit logs."""

    @pytest.mark.asyncio
    async def test_audit_logs_recorded_for_login_and_actions(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Logins and resource changes must create immutable audit records."""
        # 1. Login generates AUTH_LOGIN audit entry
        login_res = await client.post(
            "/api/v1/auth/login",
            json={"email": "admin@nvrsms.local", "password": "SuperAdmin123!"},
        )
        assert login_res.status_code == 200
        headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

        # 2. Create a new role
        role_name = f"Audit Role {uuid.uuid4().hex[:6]}"
        create_role_res = await client.post(
            "/api/v1/roles",
            headers=headers,
            json={"name": role_name, "description": "Testing audit log"},
        )
        assert create_role_res.status_code == 201
        role_id = create_role_res.json()["id"]

        # 3. Query audit logs via API
        audit_res = await client.get("/api/v1/audit", headers=headers)
        assert audit_res.status_code == 200
        logs = audit_res.json()
        assert len(logs) > 0

        actions = [log_item["action"] for log_item in logs]
        assert "AUTH_LOGIN" in actions
        assert "ROLE_CREATE" in actions

        # Verify role create entry details
        role_create_entry = next(entry for entry in logs if entry["action"] == "ROLE_CREATE")
        assert role_create_entry["resource_type"] == "role"
        assert role_create_entry["resource_id"] == role_id
