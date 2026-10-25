"""Tests for Hub metrics, deep health checks, and dashboard specifications."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from httpx import AsyncClient


class TestMetricsAndHealthObservability:
    """Tests for Prometheus metrics, health checks, and monitoring configs."""

    @pytest.mark.asyncio
    async def test_metrics_endpoint_exposition(self, client: AsyncClient) -> None:
        res = await client.get("/metrics")
        assert res.status_code == 200
        assert "text/plain" in res.headers.get("content-type", "")

        body = res.text
        assert "# HELP http_requests_total" in body
        assert "# TYPE nvrsms_agents_connected_count gauge" in body
        assert "nvrsms_agents_connected_count" in body
        assert "nvrsms_active_streams_count" in body
        assert "nvrsms_active_viewers_count" in body

    @pytest.mark.asyncio
    async def test_deep_health_endpoint_components(self, client: AsyncClient) -> None:
        res = await client.get("/health")
        assert res.status_code == 200

        data = res.json()
        assert data["status"] == "ok"
        assert "version" in data
        assert "components" in data

        components = data["components"]
        assert "database" in components
        assert components["database"]["status"] == "healthy"
        assert "redis" in components
        assert "agents" in components
        assert "streams" in components

    def test_grafana_dashboard_json_validity(self) -> None:
        dashboard_path = Path("..") / "infra" / "monitoring" / "grafana-dashboard.json"
        if not dashboard_path.exists():
            dashboard_path = Path("infra") / "monitoring" / "grafana-dashboard.json"

        assert dashboard_path.exists()
        raw = dashboard_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        assert data["title"] == "NVRSMS CCTV Platform Overview"
        assert len(data["panels"]) >= 4

    def test_alerts_yml_validity(self) -> None:
        alerts_path = Path("..") / "infra" / "monitoring" / "alerts.yml"
        if not alerts_path.exists():
            alerts_path = Path("infra") / "monitoring" / "alerts.yml"

        assert alerts_path.exists()
        content = alerts_path.read_text(encoding="utf-8")
        assert "AgentOffline" in content
        assert "HighAuthFailureRate" in content
        assert "DRRestoreVerificationFailed" in content
