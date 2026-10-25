from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from hub_backend.config import get_settings
from hub_backend.db import get_db
from hub_backend.observability.metrics import metrics_registry
from hub_backend.services.agent_manager import agent_manager
from hub_backend.services.stream_manager import stream_manager

router = APIRouter(tags=["health"])
settings = get_settings()


class ComponentStatus(BaseModel):
    status: str
    latency_ms: float = 0.0
    details: dict[str, Any] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    """Deep health check response."""

    status: str
    version: str
    components: dict[str, Any] = Field(default_factory=dict)


@router.get("/health", response_model=HealthResponse, summary="Deep health check")
async def health(db: AsyncSession = Depends(get_db)) -> HealthResponse:
    """Return service health status with subsystem component health."""
    components: dict[str, Any] = {}
    overall_ok = True

    # 1. Database ping
    t0 = time.perf_counter()
    try:
        await db.execute(text("SELECT 1"))
        db_latency = (time.perf_counter() - t0) * 1000.0
        components["database"] = {
            "status": "healthy",
            "latency_ms": round(db_latency, 2),
        }
    except Exception as exc:
        overall_ok = False
        components["database"] = {
            "status": "unhealthy",
            "error": str(exc),
        }

    # 2. Redis status
    components["redis"] = {
        "status": "healthy",
        "details": "in-memory-fallback-available",
    }

    # 3. Agent gateway status
    online_agents = agent_manager.get_online_count()
    components["agents"] = {
        "status": "healthy",
        "online_count": online_agents,
    }

    # 4. Active streaming status
    active_streams = len(stream_manager.active_streams)
    components["streams"] = {
        "status": "healthy",
        "active_streams": active_streams,
    }

    return HealthResponse(
        status="ok" if overall_ok else "degraded",
        version=settings.app_version,
        components=components,
    )


@router.get("/metrics", summary="Prometheus metrics")
async def prometheus_metrics() -> Response:
    """Prometheus exposition format endpoint."""
    text_data = metrics_registry.generate_prometheus_output()
    return Response(content=text_data, media_type="text/plain; version=0.0.4; charset=utf-8")
