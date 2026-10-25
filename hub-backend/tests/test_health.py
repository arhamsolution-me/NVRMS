"""Stage 0 tests: health endpoint and basic app setup."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


class TestHealthEndpoint:
    """Tests for the /health endpoint."""

    @pytest.mark.asyncio
    async def test_health_returns_200(self, client: AsyncClient) -> None:
        """Health endpoint must return HTTP 200."""
        response = await client.get("/health")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_health_returns_ok_status(self, client: AsyncClient) -> None:
        """Health endpoint must return status: ok."""
        response = await client.get("/health")
        data = response.json()
        assert data["status"] == "ok"

    @pytest.mark.asyncio
    async def test_health_returns_version(self, client: AsyncClient) -> None:
        """Health endpoint must return a version string."""
        response = await client.get("/health")
        data = response.json()
        assert "version" in data
        assert len(data["version"]) > 0

    @pytest.mark.asyncio
    async def test_health_includes_correlation_id(self, client: AsyncClient) -> None:
        """Response must include X-Correlation-ID header."""
        response = await client.get("/health")
        assert "x-correlation-id" in response.headers

    @pytest.mark.asyncio
    async def test_health_propagates_correlation_id(self, client: AsyncClient) -> None:
        """Server must echo the client's X-Correlation-ID."""
        my_id = "test-correlation-id-12345"
        response = await client.get("/health", headers={"X-Correlation-ID": my_id})
        assert response.headers.get("x-correlation-id") == my_id

    @pytest.mark.asyncio
    async def test_cors_header_present(self, client: AsyncClient) -> None:
        """CORS preflight must succeed for allowed origins."""
        response = await client.options(
            "/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        # Either 200 or 204 is acceptable for OPTIONS
        assert response.status_code in (200, 204)
