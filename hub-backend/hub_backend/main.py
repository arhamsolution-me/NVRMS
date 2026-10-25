"""NVRSMS Hub Backend — FastAPI Application Factory."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from hub_backend.config import get_settings
from hub_backend.logging_config import configure_logging, get_logger

# Configure logging first
configure_logging()
log = get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    """Application lifespan: startup and shutdown hooks."""
    log.info(
        "hub_starting",
        version=settings.app_version,
        env=settings.app_env,
    )
    yield
    log.info("hub_stopped")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="NVRSMS Hub",
        version=settings.app_version,
        description="Hub backend for NVRSMS CCTV platform",
        docs_url="/api/docs" if not settings.is_production else None,
        redoc_url="/api/redoc" if not settings.is_production else None,
        openapi_url="/api/openapi.json" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # ── Middleware ─────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def correlation_id_middleware(request: Request, call_next: Any) -> Response:
        """Inject a correlation ID into every request's log context."""
        correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            correlation_id=correlation_id,
            method=request.method,
            path=request.url.path,
        )
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        return response

    # ── Routes ─────────────────────────────────────────────
    from hub_backend.routes import health  # noqa: PLC0415

    app.include_router(health.router)

    return app


app = create_app()
