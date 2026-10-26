"""NVRSMS Hub Backend — FastAPI Application Factory."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

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
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: startup and shutdown hooks."""
    log.info(
        "hub_starting",
        version=settings.app_version,
        env=settings.app_env,
    )
    # Seed default data on startup
    try:
        from hub_backend.db import engine, get_db_context
        from hub_backend.models.base import Base
        import hub_backend.models  # noqa: F401
        from hub_backend.services.seed import seed_initial_data

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with get_db_context() as session:
            await seed_initial_data(session)
    except Exception as exc:
        log.warning("startup_seed_deferred", error=str(exc))

    yield

    from hub_backend.redis import close_redis

    await close_redis()
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
    from hub_backend.security.headers import SecurityHeadersMiddleware

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def correlation_id_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
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
    from hub_backend.routes import (  # noqa: PLC0415
        agent_ws_router,
        agents_router,
        audit_router,
        auth_router,
        backup_router,
        cameras_router,
        health_router,
        locations_router,
        nvrs_router,
        roles_router,
        streams_router,
        users_router,
        ws_router,
    )

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(roles_router)
    app.include_router(locations_router)
    app.include_router(users_router)
    app.include_router(audit_router)
    app.include_router(ws_router)
    app.include_router(agents_router)
    app.include_router(agent_ws_router)
    app.include_router(nvrs_router)
    app.include_router(cameras_router)
    app.include_router(streams_router)
    app.include_router(backup_router)

    return app


app = create_app()
