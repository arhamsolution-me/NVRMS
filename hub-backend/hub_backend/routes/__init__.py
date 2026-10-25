"""Routes package exporting API routers."""

from hub_backend.routes.audit import router as audit_router
from hub_backend.routes.auth import router as auth_router
from hub_backend.routes.health import router as health_router
from hub_backend.routes.locations import router as locations_router
from hub_backend.routes.roles import router as roles_router
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
]
