"""Health check routes."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from hub_backend.config import get_settings

router = APIRouter(tags=["health"])
settings = get_settings()


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    version: str


@router.get("/health", response_model=HealthResponse, summary="Health check")
async def health() -> HealthResponse:
    """Return service health status."""
    return HealthResponse(status="ok", version=settings.app_version)
