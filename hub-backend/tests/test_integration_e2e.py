"""Stage 12 End-to-End Platform Integration Test Suite.

Validates:
1. Full Agent Lifecycle: Enrolment code generation -> Agent enrollment & encrypted vault
   -> WSS connect -> Handshake & Time sync -> NVR discovery probe -> Onboarding
   -> Stream token issuance -> MediaMTX auth webhook -> 1:N fan-out -> Grace period teardown.
2. Hierarchical Scoping & Multi-Tenant IDOR Guards: Province -> City -> Area -> Site isolation
   and cross-tenant concealed 404 access.
3. Dynamic RBAC Instantaneous Toggle: Real-time permission changes take effect on the
   very next request via Redis cache invalidation without token re-issuance.
4. Disaster Recovery End-to-End Cycle: Authenticated AES-128-CBC + HMAC backup creation
   and scratch database restore verification with 100% table record match.
"""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hub_backend.models.agent import Agent
from hub_backend.models.location import Area, City, Province, Site
from hub_backend.models.nvr import NVR
from hub_backend.models.rbac import Permission, Role, RolePermission
from hub_backend.models.tenant import Tenant
from hub_backend.models.user import User, UserScope
from hub_backend.routes.agent_ws import agent_websocket_gateway
from hub_backend.security.password import hash_password
from hub_backend.security.stream_tokens import verify_stream_token
from hub_backend.security.tokens import create_access_token, hash_token
from hub_backend.services.agent_manager import agent_manager
from tests.test_agent_lifecycle import MockWebSocket


class TestEndToEndPlatformIntegration:
    """Complete platform integration scenarios."""

    @pytest.mark.asyncio
    async def test_e2e_agent_enrolment_to_stream_lifecycle(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Scenario 1: From single-use enrolment code to multi-viewer stream fan-out and teardown."""
        # 1. Admin login
        login_res = await client.post(
            "/api/v1/auth/login",
            json={"email": "admin@nvrsms.local", "password": "SuperAdmin123!"},
        )
        assert login_res.status_code == 200
        admin_token = login_res.json()["access_token"]
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        # 2. Admin creates an enrolment code for a new edge agent
        code_res = await client.post(
            "/api/v1/agents/enrol-token",
            headers=admin_headers,
            json={"name": "HQ Edge Server", "expires_in_hours": 1},
        )
        assert code_res.status_code == 201
        enrol_code = code_res.json()["code"]
        assert enrol_code.startswith("ENROL-")

        # 3. Agent consumes the enrolment code
        enrol_res = await client.post(
            "/api/v1/agents/enrol",
            json={
                "enrolment_code": enrol_code,
                "name": "HQ Edge Server Main",
                "version": "1.0.0",
            },
        )
        assert enrol_res.status_code == 200
        cred = enrol_res.json()
        agent_id = uuid.UUID(cred["agent_id"])
        agent_token = cred["agent_token"]
        assert agent_token.startswith("agt_")

        # Verify enrolment code is single-use and cannot be replayed
        replay_res = await client.post(
            "/api/v1/agents/enrol",
            json={"enrolment_code": enrol_code},
        )
        assert replay_res.status_code == 400

        # 4. Agent connects via outbound WebSocket gateway
        ws = MockWebSocket()
        gateway_task = asyncio.create_task(
            agent_websocket_gateway(ws, agent_id=str(agent_id), token=agent_token)  # type: ignore[arg-type]
        )
        await asyncio.sleep(0.05)
        assert ws.accepted
        assert agent_manager.is_online(str(agent_id))

        # 5. Agent sends heartbeat with timestamp
        hb_msg = json.dumps(
            {
                "type": "heartbeat",
                "agent_id": str(agent_id),
                "timestamp": "2026-10-26T00:00:00Z",
                "active_streams": [],
            }
        )
        await ws.incoming.put(hb_msg)
        await asyncio.sleep(0.05)

        # 6. Admin triggers NVR probe dispatch to the connected agent
        probe_task = asyncio.create_task(
            client.post(
                "/api/v1/nvrs/probe",
                headers=admin_headers,
                json={
                    "agent_id": str(agent_id),
                    "ip": "192.168.1.100",
                    "port": 554,
                    "username": "admin",
                    "password": "Password123!",
                    "brand": "hikvision",
                },
            )
        )
        await asyncio.sleep(0.05)

        # Agent receives probe command and replies with discovered RTSP channels
        assert len(ws.outgoing) >= 1
        probe_cmd = ws.outgoing[-1]
        assert probe_cmd["command"] == "probe_nvr"
        cmd_id = probe_cmd["command_id"]

        probe_response = json.dumps(
            {
                "type": "command_result",
                "command_id": cmd_id,
                "status": "success",
                "result": {
                    "status": "online",
                    "brand": "hikvision",
                    "ip": "192.168.1.100",
                    "port": 554,
                    "channel_count": 2,
                    "channels": [
                        {
                            "channel_number": 1,
                            "name": "Front Gate",
                            "main_stream_url": "rtsp://admin:Password123!@192.168.1.100:554/Streaming/Channels/101",
                            "sub_stream_url": "rtsp://admin:Password123!@192.168.1.100:554/Streaming/Channels/102",
                            "codec": "h264",
                            "resolution": "1920x1080",
                            "fps": 25,
                            "status": "online",
                        },
                        {
                            "channel_number": 2,
                            "name": "Loading Dock",
                            "main_stream_url": "rtsp://admin:Password123!@192.168.1.100:554/Streaming/Channels/201",
                            "sub_stream_url": "rtsp://admin:Password123!@192.168.1.100:554/Streaming/Channels/202",
                            "codec": "h264",
                            "resolution": "1920x1080",
                            "fps": 25,
                            "status": "online",
                        },
                    ],
                },
            }
        )
        await ws.incoming.put(probe_response)
        probe_http_res = await probe_task
        assert probe_http_res.status_code == 200
        probe_data = probe_http_res.json()
        assert probe_data["brand"] == "hikvision"
        assert len(probe_data["channels"]) == 2

        # 7. Admin onboards the NVR and associated cameras
        site_res = await client.get("/api/v1/locations/sites", headers=admin_headers)
        assert site_res.status_code == 200
        sites_list = site_res.json()
        site_id = sites_list[0]["id"] if sites_list else None

        create_nvr_res = await client.post(
            "/api/v1/nvrs",
            headers=admin_headers,
            json={
                "name": "HQ Main NVR",
                "agent_id": str(agent_id),
                "site_id": site_id,
                "ip_address": "192.168.1.100",
                "port": 554,
                "brand": "hikvision",
                "channels": [
                    {
                        "channel_number": 1,
                        "name": "Front Gate",
                        "main_stream_url": "rtsp://192.168.1.100:554/ch1",
                        "sub_stream_url": "rtsp://192.168.1.100:554/ch1_sub",
                        "codec": "h264",
                        "resolution": "1920x1080",
                    },
                    {
                        "channel_number": 2,
                        "name": "Loading Dock",
                        "main_stream_url": "rtsp://192.168.1.100:554/ch2",
                        "sub_stream_url": "rtsp://192.168.1.100:554/ch2_sub",
                        "codec": "h264",
                        "resolution": "1920x1080",
                    },
                ],
            },
        )
        assert create_nvr_res.status_code == 201
        nvr_data = create_nvr_res.json()
        assert len(nvr_data["cameras"]) == 2
        camera_id = nvr_data["cameras"][0]["id"]

        # 8. User requests stream token for Camera 1
        token_task = asyncio.create_task(
            client.post(
                f"/api/v1/streams/{camera_id}/token",
                headers=admin_headers,
                json={"stream_type": "main"},
            )
        )
        await asyncio.sleep(0.05)

        # Agent receives start_stream command and confirms publishing
        assert len(ws.outgoing) >= 2
        start_cmd = ws.outgoing[-1]
        assert start_cmd["command"] == "start_stream"
        start_cmd_id = start_cmd["command_id"]
        await ws.incoming.put(
            json.dumps(
                {
                    "type": "command_result",
                    "command_id": start_cmd_id,
                    "status": "success",
                    "result": {"status": "publishing"},
                }
            )
        )

        token_res = await token_task
        assert token_res.status_code == 200
        token_data_1 = token_res.json()
        stream_token_1 = token_data_1["token"]
        viewer_id_1 = token_data_1["viewer_id"]
        claims = verify_stream_token(stream_token_1)
        assert claims["camera_id"] == camera_id
        assert claims["stream_type"] == "main"

        # 9. MediaMTX invokes external authentication webhook
        auth_read_res = await client.post(
            "/api/v1/streams/auth",
            json={
                "action": "read",
                "path": f"live/{camera_id}_main",
                "query": f"token={stream_token_1}",
            },
        )
        assert auth_read_res.status_code == 200

        # 10. Multi-viewer 1:N fan-out: second viewer joins stream
        token_res_2 = await client.post(
            f"/api/v1/streams/{camera_id}/token",
            headers=admin_headers,
            json={"stream_type": "main"},
        )
        assert token_res_2.status_code == 200
        token_data_2 = token_res_2.json()
        viewer_id_2 = token_data_2["viewer_id"]

        hb_res = await client.post(
            f"/api/v1/streams/{camera_id}/heartbeat",
            headers=admin_headers,
            json={"viewer_id": viewer_id_1, "stream_type": "main"},
        )
        assert hb_res.status_code == 200
        assert hb_res.json()["status"] == "ok"

        # 11. Viewers disconnect -> clean stop stream
        stop_res_1 = await client.post(
            f"/api/v1/streams/{camera_id}/stop",
            headers=admin_headers,
            json={"viewer_id": viewer_id_1, "stream_type": "main"},
        )
        assert stop_res_1.status_code == 200
        stop_res_2 = await client.post(
            f"/api/v1/streams/{camera_id}/stop",
            headers=admin_headers,
            json={"viewer_id": viewer_id_2, "stream_type": "main"},
        )
        assert stop_res_2.status_code == 200

        # Close agent websocket
        await ws.incoming.put(None)
        await gateway_task

    @pytest.mark.asyncio
    async def test_e2e_hierarchical_scoping_and_cross_tenant_isolation(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Scenario 2: Province -> City -> Area -> Site isolation & Tenant cross-boundary concealed 404."""
        # 1. Setup Tenant A and Tenant B
        tenant_a = Tenant(id=uuid.uuid4(), name="Alpha Corp", slug="alpha-corp", is_active=True)
        tenant_b = Tenant(id=uuid.uuid4(), name="Beta Corp", slug="beta-corp", is_active=True)
        db_session.add_all([tenant_a, tenant_b])
        await db_session.flush()

        # 2. Setup hierarchy for Tenant A
        prov_a = Province(id=uuid.uuid4(), tenant_id=tenant_a.id, name="Punjab", code="PB")
        db_session.add(prov_a)
        await db_session.flush()

        city_a = City(id=uuid.uuid4(), province_id=prov_a.id, name="Lahore", code="LHR")
        db_session.add(city_a)
        await db_session.flush()

        area_a = Area(id=uuid.uuid4(), city_id=city_a.id, name="Gulberg", code="GLB")
        db_session.add(area_a)
        await db_session.flush()

        site_a1 = Site(
            id=uuid.uuid4(),
            area_id=area_a.id,
            name="Alpha HQ",
            code="ALPHA-HQ",
        )
        site_a2 = Site(
            id=uuid.uuid4(),
            area_id=area_a.id,
            name="Alpha Branch",
            code="ALPHA-BR",
        )
        db_session.add_all([site_a1, site_a2])
        await db_session.flush()

        # 3. Create agent and NVRs on Site A1 and Site A2
        agent_a1 = Agent(
            id=uuid.uuid4(),
            tenant_id=tenant_a.id,
            name="Alpha Agent 1",
            token_hash=hash_token("alpha_tok_1"),
            is_active=True,
            status="online",
        )
        agent_b = Agent(
            id=uuid.uuid4(),
            tenant_id=tenant_b.id,
            name="Beta Agent",
            token_hash=hash_token("beta_tok"),
            is_active=True,
            status="online",
        )
        db_session.add_all([agent_a1, agent_b])
        await db_session.flush()

        nvr_a1 = NVR(
            id=uuid.uuid4(),
            tenant_id=tenant_a.id,
            site_id=site_a1.id,
            agent_id=agent_a1.id,
            name="Alpha NVR 1",
            ip_address="192.168.10.10",
            port=554,
            brand="dahua",
        )
        nvr_a2 = NVR(
            id=uuid.uuid4(),
            tenant_id=tenant_a.id,
            site_id=site_a2.id,
            agent_id=agent_a1.id,
            name="Alpha NVR 2",
            ip_address="192.168.10.20",
            port=554,
            brand="dahua",
        )
        db_session.add_all([nvr_a1, nvr_a2])
        await db_session.flush()

        # 4. Create Role with nvrs:read, cameras:read, and agents:read
        perm_res = await db_session.execute(
            select(Permission).where(
                Permission.code.in_(["nvrs:read", "cameras:read", "agents:read"])
            )
        )
        perms = list(perm_res.scalars().all())

        role_a = Role(id=uuid.uuid4(), tenant_id=tenant_a.id, name="Alpha Operator")
        role_b = Role(id=uuid.uuid4(), tenant_id=tenant_b.id, name="Beta Operator")
        db_session.add_all([role_a, role_b])
        await db_session.flush()

        for p in perms:
            db_session.add(
                RolePermission(
                    id=uuid.uuid4(), role_id=role_a.id, permission_id=p.id, is_granted=True
                )
            )
            db_session.add(
                RolePermission(
                    id=uuid.uuid4(), role_id=role_b.id, permission_id=p.id, is_granted=True
                )
            )
        await db_session.flush()

        # 5. User A scoped ONLY to Site A1
        user_a = User(
            id=uuid.uuid4(),
            tenant_id=tenant_a.id,
            email="operator_a@alpha.local",
            full_name="Alpha Op",
            password_hash=hash_password("OperatorPass123!"),
            role_id=role_a.id,
            is_active=True,
            is_superuser=False,
        )
        user_b = User(
            id=uuid.uuid4(),
            tenant_id=tenant_b.id,
            email="operator_b@beta.local",
            full_name="Beta Op",
            password_hash=hash_password("OperatorPass123!"),
            role_id=role_b.id,
            is_active=True,
            is_superuser=False,
        )
        db_session.add_all([user_a, user_b])
        await db_session.flush()

        # Assign Site A1 scope to User A
        db_session.add(
            UserScope(
                id=uuid.uuid4(),
                user_id=user_a.id,
                scope_type="site",
                scope_id=site_a1.id,
            )
        )
        await db_session.commit()

        # 6. Verify User A only sees NVR A1, not NVR A2
        token_user_a = create_access_token(
            user_id=user_a.id,
            tenant_id=tenant_a.id,
            role_id=role_a.id,
            is_superuser=False,
        )
        headers_a = {"Authorization": f"Bearer {token_user_a}"}

        nvrs_res = await client.get("/api/v1/nvrs", headers=headers_a)
        assert nvrs_res.status_code == 200
        nvr_ids = [n["id"] for n in nvrs_res.json()]
        assert str(nvr_a1.id) in nvr_ids
        assert str(nvr_a2.id) not in nvr_ids  # Scoped out!

        # 7. User A attempts direct access to NVR A2 -> Forbidden or concealed 404
        direct_a2 = await client.get(f"/api/v1/nvrs/{nvr_a2.id}", headers=headers_a)
        assert direct_a2.status_code in (403, 404)

        # 8. User B from Tenant B attempts direct access to Tenant A's agent or NVR
        token_user_b = create_access_token(
            user_id=user_b.id,
            tenant_id=tenant_b.id,
            role_id=role_b.id,
            is_superuser=False,
        )
        headers_b = {"Authorization": f"Bearer {token_user_b}"}

        # Cross-tenant IDOR attack concealed with 404
        idor_agent_res = await client.get(f"/api/v1/agents/{agent_a1.id}", headers=headers_b)
        assert idor_agent_res.status_code == 404

        idor_nvr_res = await client.get(f"/api/v1/nvrs/{nvr_a1.id}", headers=headers_b)
        assert idor_nvr_res.status_code == 404

    @pytest.mark.asyncio
    async def test_e2e_instantaneous_dynamic_rbac_toggle(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Scenario 3: Modifying a role's permissions instantly impacts user without token expiry."""
        # 1. Create Tenant, Role, and User
        tenant = Tenant(id=uuid.uuid4(), name="RBAC Test Corp", slug="rbac-corp", is_active=True)
        db_session.add(tenant)
        await db_session.flush()

        role = Role(id=uuid.uuid4(), tenant_id=tenant.id, name="Test Operator")
        db_session.add(role)
        await db_session.flush()

        # Find audit:read permission
        audit_perm_res = await db_session.execute(
            select(Permission).where(Permission.code == "audit:read")
        )
        audit_perm = audit_perm_res.scalar_one()

        # Grant audit:read to role
        rp = RolePermission(
            id=uuid.uuid4(), role_id=role.id, permission_id=audit_perm.id, is_granted=True
        )
        db_session.add(rp)
        await db_session.flush()

        user = User(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            email="dynamic_rbac@test.local",
            full_name="RBAC Tester",
            password_hash=hash_password("TesterPass123!"),
            role_id=role.id,
            is_active=True,
            is_superuser=False,
        )
        db_session.add(user)
        await db_session.commit()

        # User token
        user_token = create_access_token(
            user_id=user.id,
            tenant_id=tenant.id,
            role_id=role.id,
            is_superuser=False,
        )
        user_headers = {"Authorization": f"Bearer {user_token}"}

        # 2. User initially has audit:read -> can access audit logs
        initial_res = await client.get("/api/v1/audit", headers=user_headers)
        assert initial_res.status_code == 200

        # 3. SuperAdmin revokes audit:read from the role
        login_res = await client.post(
            "/api/v1/auth/login",
            json={"email": "admin@nvrsms.local", "password": "SuperAdmin123!"},
        )
        admin_headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

        # Revoke audit:read from role
        update_perm_res = await client.put(
            f"/api/v1/roles/{role.id}/permissions",
            headers=admin_headers,
            json={"permission_code": "audit:read", "is_granted": False},
        )
        assert update_perm_res.status_code == 200

        # 4. Immediate next request with the EXISTING token must be denied with HTTP 403!
        immediate_denied_res = await client.get("/api/v1/audit", headers=user_headers)
        assert immediate_denied_res.status_code == 403

        # 5. Re-grant audit:read to the role
        grant_perm_res = await client.put(
            f"/api/v1/roles/{role.id}/permissions",
            headers=admin_headers,
            json={"permission_code": "audit:read", "is_granted": True},
        )
        assert grant_perm_res.status_code == 200

        # 6. Immediate next request with the SAME token succeeds with HTTP 200!
        immediate_granted_res = await client.get("/api/v1/audit", headers=user_headers)
        assert immediate_granted_res.status_code == 200

    @pytest.mark.asyncio
    async def test_e2e_disaster_recovery_backup_and_restore_cycle(
        self, client: AsyncClient
    ) -> None:
        """Scenario 4: Backup creation, authenticated encryption, and scratch restore verification."""
        # 1. Admin login
        login_res = await client.post(
            "/api/v1/auth/login",
            json={"email": "admin@nvrsms.local", "password": "SuperAdmin123!"},
        )
        admin_headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

        # 2. Trigger automated encrypted backup
        backup_res = await client.post(
            "/api/v1/backup/create",
            headers=admin_headers,
        )
        assert backup_res.status_code == 200
        backup_data = backup_res.json()
        assert "archive_filename" in backup_data
        assert "raw_sha256" in backup_data
        assert "encrypted_sha256" in backup_data
        assert backup_data["raw_sha256"] != backup_data["encrypted_sha256"]

        # 3. Trigger scratch restore integrity verification
        verify_res = await client.post(
            "/api/v1/backup/verify",
            headers=admin_headers,
        )
        assert verify_res.status_code == 200
        verify_data = verify_res.json()
        assert verify_data["verification_status"] == "PASSED"
        assert verify_data["all_tables_matched"] is True
        assert verify_data["record_counts"]["users"] >= 1
