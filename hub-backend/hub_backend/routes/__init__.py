"""Routes package exporting API routers."""

from hub_backend.routes.agent_ws import router as agent_ws_router
from hub_backend.routes.agents import router as agents_router
from hub_backend.routes.audit import router as audit_router
from hub_backend.routes.auth import router as auth_router
from hub_backend.routes.backup import router as backup_router
from hub_backend.routes.cameras import router as cameras_router
from hub_backend.routes.health import router as health_router
from hub_backend.routes.locations import router as locations_router
from hub_backend.routes.nvrs import router as nvrs_router
from hub_backend.routes.roles import router as roles_router
from hub_backend.routes.streams import router as streams_router
from hub_backend.routes.users import router as users_router
from hub_backend.routes.ws import router as ws_router

__all__ = [
    "health_router",
    "auth_router",
    "roles_router",
    "locations_router",
    "users_router",
    "audit_router",
    "ws_router",
    "agents_router",
    "agent_ws_router",
    "nvrs_router",
    "cameras_router",
    "streams_router",
    "backup_router",
]
