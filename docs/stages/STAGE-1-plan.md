# CCTV Hub & Agent Platform — Stage 1 Plan

## Stage: Hub Core (Auth, Tenants, RBAC, Locations, Audit)

### Objective
Implement the complete core authorization and data isolation engine for the NVRSMS platform:
- Multi-tenancy and User scoping
- Location hierarchy: Province -> City -> Area -> Site
- Roles, granular toggle-able Permissions, Role-Permission mappings
- Authentication: Argon2id password hashing, JWT access tokens (15m), rotating refresh tokens in HTTP-only secure cookies, account lockout after failed attempts, rate limiting, optional TOTP (pyotp)
- Permission check dependency `require_permission(permission_code)` with versioned Redis caching and WebSocket notification (`permissions_changed`)
- Data scoping: Users scoped to specific locations/sites cannot access resources outside their scope
- Last super-admin protection: Cannot delete or remove super-admin role from the last active super-admin
- Structured Audit Log for all security and administrative mutations
- `/me` endpoint returning profile, effective permissions, scopes, and tenant info
- Auto-seeding of default permissions, Super Admin role, and root tenant/user on startup

### Files to Create / Modify

#### Database & Models (`hub_backend/models/`)
- `base.py` — TimestampedBase with UUID primary keys
- `tenant.py` — `Tenant`
- `location.py` — `Province`, `City`, `Area`, `Site`
- `rbac.py` — `Role`, `Permission`, `RolePermission`
- `user.py` — `User`, `UserScope` (binding user to tenant/province/city/area/site), `RefreshToken`
- `audit.py` — `AuditLog`
- `alembic/versions/0002_hub_core.py` — Schema migration for all Stage 1 models

#### Security & Auth Services (`hub_backend/security/` and `hub_backend/services/`)
- `hub_backend/security/password.py` — Argon2id password hasher and verifier
- `hub_backend/security/tokens.py` — JWT generator/decoder, rotating refresh token store/hash
- `hub_backend/security/totp.py` — TOTP secret generation, verification, recovery codes
- `hub_backend/security/rbac.py` — `require_permission(code)` dependency, Redis-backed permission cache with versioning
- `hub_backend/security/scoping.py` — Location and tenant scope filters for SQLAlchemy queries
- `hub_backend/services/audit.py` — Structured audit logging service
- `hub_backend/services/auth.py` — Login, lockout tracking, refresh rotation, logout, TOTP enable/verify
- `hub_backend/services/seed.py` — Seed initial permissions, Super Admin role, root user

#### Routes & Schemas (`hub_backend/schemas/` & `hub_backend/routes/`)
- `hub_backend/schemas/auth.py` — LoginRequest, TokenResponse, MeResponse, TOTP setup schemas
- `hub_backend/schemas/rbac.py` — Role, Permission, RolePermission toggle schemas
- `hub_backend/schemas/location.py` — Province, City, Area, Site schemas
- `hub_backend/schemas/user.py` — UserCreate, UserUpdate, UserResponse schemas
- `hub_backend/routes/auth.py` — `/api/v1/auth/login`, `/refresh`, `/logout`, `/me`, `/totp/setup`, `/totp/verify`
- `hub_backend/routes/roles.py` — `/api/v1/roles`, `/api/v1/roles/{id}/permissions` (instant toggle)
- `hub_backend/routes/locations.py` — `/api/v1/locations/...`
- `hub_backend/routes/users.py` — `/api/v1/users/...`
- `hub_backend/routes/audit.py` — `/api/v1/audit/...`
- `hub_backend/ws/events.py` — WebSocket event bus for instant `permissions_changed` broadcasts

#### Tests (`hub-backend/tests/`)
- `test_auth.py` — Argon2id, login success, bad credentials, lockout, rotating refresh token reuse rejection, TOTP
- `test_rbac.py` — Permission allow/deny, instant permission toggle effect on next request, versioned cache invalidation
- `test_scoping.py` — User in Site A cannot view Site B even by guessing UUID, multi-tenant isolation
- `test_superadmin_protection.py` — Last super-admin deletion or demotion blocked with 400
- `test_audit.py` — Audit logs created for logins, permission toggles, role modifications

### Exit Gate Criteria
- [ ] Toggling off a permission instantly revokes access on the next request for all users with that role
- [ ] Scoped user in Site A receives 403/404 when attempting to access Site B resources
- [ ] Attempting to delete or demote the last super-admin fails closed
- [ ] Refresh token reuse is detected and revokes token family
- [ ] All audit operations are properly logged
- [ ] 100% of new and regression tests pass with >=80% coverage
