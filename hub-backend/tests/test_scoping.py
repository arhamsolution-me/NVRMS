"""Stage 1 tests: Location scoping, site isolation, and multi-tenant security."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hub_backend.models.location import Area, City, Province, Site
from hub_backend.models.rbac import Role
from hub_backend.models.tenant import Tenant
from hub_backend.models.user import User, UserScope
from hub_backend.security.password import hash_password


class TestLocationScoping:
    """Tests for hierarchical location scoping and cross-site access denial."""

    @pytest.mark.asyncio
    async def test_site_scope_isolation_and_cross_site_blocked(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """User scoped to Site A cannot view Site B, even by guessing its UUID."""
        # 1. Setup tenant & locations
        tenant = (await db_session.execute(select(Tenant).limit(1))).scalar_one()
        role = (await db_session.execute(select(Role).where(Role.name == "Viewer"))).scalar_one()

        prov = Province(tenant_id=tenant.id, name="Punjab", code="PB")
        db_session.add(prov)
        await db_session.flush()

        city = City(province_id=prov.id, name="Lahore", code="LHR")
        db_session.add(city)
        await db_session.flush()

        area = Area(city_id=city.id, name="Gulberg", code="GLB")
        db_session.add(area)
        await db_session.flush()

        site_a = Site(area_id=area.id, name="Branch Office A", code="SITE-A")
        site_b = Site(area_id=area.id, name="Branch Office B", code="SITE-B")
        db_session.add_all([site_a, site_b])
        await db_session.flush()

        # 2. Create user scoped strictly to Site A
        user_email = f"scoped_{uuid.uuid4().hex[:8]}@test.local"
        scoped_user = User(
            tenant_id=tenant.id,
            email=user_email,
            password_hash=hash_password("Password123!"),
            full_name="Site A Guard",
            role_id=role.id,
            is_active=True,
            is_superuser=False,
        )
        db_session.add(scoped_user)
        await db_session.flush()

        # Assign scope ONLY to site_a
        scope_a = UserScope(
            user_id=scoped_user.id,
            scope_type="site",
            scope_id=site_a.id,
        )
        db_session.add(scope_a)
        await db_session.commit()

        # 3. Log in as scoped user
        login_res = await client.post(
            "/api/v1/auth/login",
            json={"email": user_email, "password": "Password123!"},
        )
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 4. List sites: should ONLY return Site A, never Site B
        list_res = await client.get("/api/v1/locations/sites", headers=headers)
        assert list_res.status_code == 200
        sites_data = list_res.json()
        returned_ids = [s["id"] for s in sites_data]
        assert str(site_a.id) in returned_ids
        assert str(site_b.id) not in returned_ids

        # 5. Access Site A directly by UUID -> 200 OK
        res_a = await client.get(f"/api/v1/locations/sites/{site_a.id}", headers=headers)
        assert res_a.status_code == 200
        assert res_a.json()["code"] == "SITE-A"

        # 6. Attempt to access Site B directly by guessing UUID -> 403 Forbidden!
        res_b = await client.get(f"/api/v1/locations/sites/{site_b.id}", headers=headers)
        assert res_b.status_code == 403
        assert "outside user authorized scope" in res_b.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_cross_tenant_isolation(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """User in Tenant 1 attempting to access resources in Tenant 2 receives 404."""
        # Create second tenant
        tenant_2 = Tenant(name="Tenant Two", slug=f"t2_{uuid.uuid4().hex[:6]}", is_active=True)
        db_session.add(tenant_2)
        await db_session.flush()

        prov_2 = Province(tenant_id=tenant_2.id, name="Sindh", code="SND")
        db_session.add(prov_2)
        await db_session.flush()

        city_2 = City(province_id=prov_2.id, name="Karachi", code="KHI")
        db_session.add(city_2)
        await db_session.flush()

        area_2 = Area(city_id=city_2.id, name="Clifton", code="CLF")
        db_session.add(area_2)
        await db_session.flush()

        site_c = Site(area_id=area_2.id, name="Site C", code="SITE-C")
        db_session.add(site_c)
        await db_session.commit()

        # Log in as user in Tenant 1
        tenant_1 = (
            await db_session.execute(select(Tenant).where(Tenant.slug == "default"))
        ).scalar_one()
        role = (await db_session.execute(select(Role).where(Role.name == "Viewer"))).scalar_one()

        t1_user_email = f"t1_user_{uuid.uuid4().hex[:8]}@test.local"
        t1_user = User(
            tenant_id=tenant_1.id,
            email=t1_user_email,
            password_hash=hash_password("Password123!"),
            full_name="Tenant 1 User",
            role_id=role.id,
            is_active=True,
            is_superuser=False,
        )
        db_session.add(t1_user)
        await db_session.commit()

        login_res = await client.post(
            "/api/v1/auth/login",
            json={"email": t1_user_email, "password": "Password123!"},
        )
        t1_headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

        # Attempt to access Site C in Tenant 2 by UUID -> 404 (concealed)
        res = await client.get(f"/api/v1/locations/sites/{site_c.id}", headers=t1_headers)
        assert res.status_code == 404

    @pytest.mark.asyncio
    async def test_hierarchical_scopes_province_city_area(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """User scoped at Province or City or Area level inherits access to all child sites."""
        tenant = (await db_session.execute(select(Tenant).limit(1))).scalar_one()
        role = (await db_session.execute(select(Role).where(Role.name == "Viewer"))).scalar_one()

        prov = Province(tenant_id=tenant.id, name="KPK", code="KPK")
        db_session.add(prov)
        await db_session.flush()

        city = City(province_id=prov.id, name="Peshawar", code="PEW")
        db_session.add(city)
        await db_session.flush()

        area = Area(city_id=city.id, name="Hayatabad", code="HYT")
        db_session.add(area)
        await db_session.flush()

        site = Site(area_id=area.id, name="HQ Site", code="HQ-1")
        db_session.add(site)
        await db_session.flush()

        # Create user scoped by Province
        prov_user = User(
            tenant_id=tenant.id,
            email=f"prov_user_{uuid.uuid4().hex[:6]}@test.local",
            password_hash=hash_password("Password123!"),
            full_name="Province Supervisor",
            role_id=role.id,
            is_active=True,
            is_superuser=False,
        )
        db_session.add(prov_user)
        await db_session.flush()
        db_session.add(UserScope(user_id=prov_user.id, scope_type="province", scope_id=prov.id))
        await db_session.commit()

        login_res = await client.post(
            "/api/v1/auth/login",
            json={"email": prov_user.email, "password": "Password123!"},
        )
        headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

        # Province supervisor can access child site
        res = await client.get(f"/api/v1/locations/sites/{site.id}", headers=headers)
        assert res.status_code == 200
        assert res.json()["code"] == "HQ-1"
