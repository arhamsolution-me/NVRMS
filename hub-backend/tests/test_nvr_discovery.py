"""Stage 3 Hub tests: NVR Probe, Onboarding, Multi-Agent IP isolation, Scoping, and Camera CRUD."""

from __future__ import annotations

import asyncio
import json

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hub_backend.models.agent import Agent
from hub_backend.models.camera import Camera
from hub_backend.models.location import Area, City, Province, Site
from hub_backend.models.nvr import NVR
from hub_backend.models.tenant import Tenant
from hub_backend.models.user import User, UserScope
from hub_backend.routes.agent_ws import agent_websocket_gateway
from hub_backend.security.tokens import hash_token
from tests.test_agent_lifecycle import MockWebSocket


class TestNVRDiscoveryAndOnboarding:
    """Tests for NVR probe command dispatch, creation, duplicate checks, and multi-agent isolation."""

    @pytest.mark.asyncio
    async def test_nvr_probe_dispatch_to_connected_agent(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Admin triggers probe; agent receives probe_nvr command and returns channel discovery."""
        # 1. Admin login
        login_res = await client.post(
            "/api/v1/auth/login",
            json={"email": "admin@nvrsms.local", "password": "SuperAdmin123!"},
        )
        headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

        # 2. Setup connected agent
        tenant = (await db_session.execute(select(Tenant).limit(1))).scalar_one()
        raw_token = "agt_probe_test_token"
        agent = Agent(
            tenant_id=tenant.id,
            name="Probe Agent 1",
            token_hash=hash_token(raw_token),
            is_active=True,
            status="offline",
        )
        db_session.add(agent)
        await db_session.commit()

        ws = MockWebSocket()
        gw_task = asyncio.create_task(
            agent_websocket_gateway(ws, agent_id=str(agent.id), token=raw_token)  # type: ignore[arg-type]
        )
        await asyncio.sleep(0.05)
        assert ws.accepted

        # 3. Trigger probe request from admin in background
        probe_task = asyncio.create_task(
            client.post(
                "/api/v1/nvrs/probe",
                headers=headers,
                json={
                    "agent_id": str(agent.id),
                    "ip": "192.168.1.100",
                    "port": 554,
                    "username": "admin",
                    "password": "pass",
                    "brand": "hikvision",
                },
            )
        )
        await asyncio.sleep(0.05)

        # 4. Agent receives probe_nvr command
        assert len(ws.outgoing) >= 1
        cmd_envelope = ws.outgoing[-1]
        assert cmd_envelope["command"] == "probe_nvr"
        cmd_id = cmd_envelope["command_id"]

        # 5. Agent sends back discovery result
        mock_result = {
            "type": "command_result",
            "command_id": cmd_id,
            "status": "success",
            "result": {
                "status": "success",
                "brand": "hikvision",
                "model": "DS-7608NI-K2",
                "serial_number": "DS-7608NI-123456",
                "mac_address": "C0:56:E3:01:02:03",
                "ip": "192.168.1.100",
                "port": 554,
                "channel_count": 2,
                "channels": [
                    {
                        "channel_number": 1,
                        "name": "Front Entrance",
                        "main_stream_url": "rtsp://admin:pass@192.168.1.100:554/Streaming/Channels/101",
                        "sub_stream_url": "rtsp://admin:pass@192.168.1.100:554/Streaming/Channels/102",
                        "codec": "h264",
                        "resolution": "1920x1080",
                        "fps": 25,
                        "status": "online",
                    },
                    {
                        "channel_number": 2,
                        "name": "Loading Bay",
                        "main_stream_url": "rtsp://admin:pass@192.168.1.100:554/Streaming/Channels/201",
                        "sub_stream_url": "rtsp://admin:pass@192.168.1.100:554/Streaming/Channels/202",
                        "codec": "h265",
                        "resolution": "2560x1440",
                        "fps": 30,
                        "status": "online",
                    },
                ],
                "diagnostics": {"reachable": True},
            },
        }
        await ws.incoming.put(json.dumps(mock_result))

        # 6. Admin receives probe response
        res = await probe_task
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert data["brand"] == "hikvision"
        assert data["channel_count"] == 2
        assert len(data["channels"]) == 2
        assert data["channels"][0]["name"] == "Front Entrance"

        # Disconnect ws
        await ws.incoming.put(None)
        await gw_task

    @pytest.mark.asyncio
    async def test_nvr_duplicate_rejected_and_multi_agent_same_ip_allowed(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Same IP on same agent is rejected (409); same IP on two different agents is allowed."""
        login_res = await client.post(
            "/api/v1/auth/login",
            json={"email": "admin@nvrsms.local", "password": "SuperAdmin123!"},
        )
        headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

        tenant = (await db_session.execute(select(Tenant).limit(1))).scalar_one()

        # Create Agent 1 and Agent 2
        agent1 = Agent(
            tenant_id=tenant.id,
            name="Warehouse Agent",
            token_hash=hash_token("tok_agent1"),
            is_active=True,
            status="offline",
        )
        agent2 = Agent(
            tenant_id=tenant.id,
            name="HQ Agent",
            token_hash=hash_token("tok_agent2"),
            is_active=True,
            status="offline",
        )
        db_session.add_all([agent1, agent2])
        await db_session.commit()

        nvr_payload = {
            "agent_id": str(agent1.id),
            "name": "Warehouse NVR 1",
            "brand": "hikvision",
            "ip_address": "192.168.1.200",
            "port": 554,
            "channels": [
                {
                    "channel_number": 1,
                    "name": "Gate Camera",
                    "main_stream_url": "rtsp://192.168.1.200:554/Streaming/Channels/101",
                }
            ],
        }

        # 1. First add on Agent 1 succeeds
        res1 = await client.post("/api/v1/nvrs", headers=headers, json=nvr_payload)
        assert res1.status_code == 201
        nvr1_id = res1.json()["id"]

        # 2. Duplicate add on Agent 1 with same IP:port returns 409 Conflict
        res_dup = await client.post("/api/v1/nvrs", headers=headers, json=nvr_payload)
        assert res_dup.status_code == 409
        assert "already registered" in res_dup.json()["detail"].lower()

        # 3. Same IP:port on Agent 2 SUCCEEDS (isolated local networks on different edge sites)
        nvr_payload_agent2 = dict(nvr_payload)
        nvr_payload_agent2["agent_id"] = str(agent2.id)
        nvr_payload_agent2["name"] = "HQ NVR with identical IP"

        res_agent2 = await client.post("/api/v1/nvrs", headers=headers, json=nvr_payload_agent2)
        assert res_agent2.status_code == 201
        nvr2_id = res_agent2.json()["id"]
        assert nvr1_id != nvr2_id


class TestNVRScopingAndCRUD:
    """Tests for location scoping on NVRs/cameras and CRUD operations."""

    @pytest.mark.asyncio
    async def test_location_scoping_on_nvrs_and_cameras(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Scoped user can only see NVRs and Cameras in their assigned site."""
        tenant = (await db_session.execute(select(Tenant).limit(1))).scalar_one()

        # Create two distinct sites
        prov = Province(tenant_id=tenant.id, name="Test Province", code="TP")
        db_session.add(prov)
        await db_session.flush()
        city = City(province_id=prov.id, name="Test City", code="TC")
        db_session.add(city)
        await db_session.flush()
        area = Area(city_id=city.id, name="Test Area", code="TA")
        db_session.add(area)
        await db_session.flush()

        site_a = Site(area_id=area.id, name="Site Alpha", code="S-A")
        site_b = Site(area_id=area.id, name="Site Beta", code="S-B")
        db_session.add_all([site_a, site_b])
        await db_session.flush()

        # Create Agent
        agent = Agent(
            tenant_id=tenant.id,
            name="Scoping Agent",
            token_hash=hash_token("tok_scoping_agent"),
            is_active=True,
            status="offline",
        )
        db_session.add(agent)
        await db_session.flush()

        # Create NVR on Site A and NVR on Site B
        nvr_a = NVR(
            tenant_id=tenant.id,
            site_id=site_a.id,
            agent_id=agent.id,
            name="NVR Alpha",
            ip_address="10.0.1.10",
            port=554,
        )
        nvr_b = NVR(
            tenant_id=tenant.id,
            site_id=site_b.id,
            agent_id=agent.id,
            name="NVR Beta",
            ip_address="10.0.2.10",
            port=554,
        )
        db_session.add_all([nvr_a, nvr_b])
        await db_session.flush()

        # Create Camera on Site A and Camera on Site B
        cam_a = Camera(
            tenant_id=tenant.id,
            site_id=site_a.id,
            nvr_id=nvr_a.id,
            channel_number=1,
            name="Alpha Cam 1",
            main_stream_url="rtsp://10.0.1.10/ch1",
        )
        cam_b = Camera(
            tenant_id=tenant.id,
            site_id=site_b.id,
            nvr_id=nvr_b.id,
            channel_number=1,
            name="Beta Cam 1",
            main_stream_url="rtsp://10.0.2.10/ch1",
        )
        db_session.add_all([cam_a, cam_b])
        await db_session.commit()

        # Create scoped user restricted ONLY to Site Alpha
        from hub_backend.models.rbac import Role

        viewer_role = (
            await db_session.execute(select(Role).where(Role.name == "Viewer"))
        ).scalar_one()

        scoped_user = User(
            tenant_id=tenant.id,
            role_id=viewer_role.id,
            email="site_a_guard@nvrsms.local",
            password_hash="mock_hash",
            full_name="Site A Guard",
            is_active=True,
            is_superuser=False,
        )
        db_session.add(scoped_user)
        await db_session.flush()

        scope = UserScope(
            user_id=scoped_user.id,
            scope_type="site",
            scope_id=site_a.id,
        )
        db_session.add(scope)
        await db_session.commit()

        # Generate token for scoped user
        from hub_backend.security.tokens import create_access_token

        user_token = create_access_token(
            user_id=scoped_user.id,
            tenant_id=tenant.id,
            role_id=viewer_role.id,
            is_superuser=False,
        )
        user_headers = {"Authorization": f"Bearer {user_token}"}

        # 1. Scoped user sees NVR Alpha, but NOT NVR Beta
        list_nvrs_res = await client.get("/api/v1/nvrs", headers=user_headers)
        assert list_nvrs_res.status_code == 200
        nvr_ids = [n["id"] for n in list_nvrs_res.json()]
        assert str(nvr_a.id) in nvr_ids
        assert str(nvr_b.id) not in nvr_ids

        # 2. Scoped user directly accessing NVR Beta returns 404 (concealed)
        detail_b_res = await client.get(f"/api/v1/nvrs/{nvr_b.id}", headers=user_headers)
        assert detail_b_res.status_code == 404

        # 3. Scoped user sees Camera Alpha, but NOT Camera Beta
        list_cams_res = await client.get("/api/v1/cameras", headers=user_headers)
        assert list_cams_res.status_code == 200
        cam_ids = [c["id"] for c in list_cams_res.json()]
        assert str(cam_a.id) in cam_ids
        assert str(cam_b.id) not in cam_ids

        # 4. Scoped user directly accessing Camera Beta returns 404
        cam_b_res = await client.get(f"/api/v1/cameras/{cam_b.id}", headers=user_headers)
        assert cam_b_res.status_code == 404

    @pytest.mark.asyncio
    async def test_nvr_crud_lifecycle_and_cascade_delete(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """NVR update updates fields; deleting NVR cascades and removes attached cameras."""
        login_res = await client.post(
            "/api/v1/auth/login",
            json={"email": "admin@nvrsms.local", "password": "SuperAdmin123!"},
        )
        headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

        tenant = (await db_session.execute(select(Tenant).limit(1))).scalar_one()
        agent = Agent(
            tenant_id=tenant.id,
            name="CRUD Agent",
            token_hash=hash_token("tok_crud_agent"),
            is_active=True,
            status="offline",
        )
        db_session.add(agent)
        await db_session.commit()

        # Create NVR with 2 cameras
        create_res = await client.post(
            "/api/v1/nvrs",
            headers=headers,
            json={
                "agent_id": str(agent.id),
                "name": "NVR To Delete",
                "ip_address": "192.168.5.50",
                "port": 554,
                "channels": [
                    {"channel_number": 1, "name": "Cam 1", "main_stream_url": "rtsp://test/1"},
                    {"channel_number": 2, "name": "Cam 2", "main_stream_url": "rtsp://test/2"},
                ],
            },
        )
        assert create_res.status_code == 201
        nvr_id = create_res.json()["id"]
        cam_ids = [c["id"] for c in create_res.json()["cameras"]]
        assert len(cam_ids) == 2

        # Update NVR
        patch_res = await client.patch(
            f"/api/v1/nvrs/{nvr_id}",
            headers=headers,
            json={"name": "NVR Renamed"},
        )
        assert patch_res.status_code == 200
        assert patch_res.json()["name"] == "NVR Renamed"

        # Delete NVR
        del_res = await client.delete(f"/api/v1/nvrs/{nvr_id}", headers=headers)
        assert del_res.status_code == 200

        # NVR is gone
        assert (await client.get(f"/api/v1/nvrs/{nvr_id}", headers=headers)).status_code == 404

        # Cameras are cascaded and gone
        for cid in cam_ids:
            assert (await client.get(f"/api/v1/cameras/{cid}", headers=headers)).status_code == 404
