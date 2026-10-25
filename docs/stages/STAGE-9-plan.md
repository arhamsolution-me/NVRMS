# CCTV Hub & Agent Platform — Stage 9 Plan

## Stage: Frontend Foundation

### Objective
Build a modern, high-performance, visually stunning React 19 + TypeScript frontend foundation for the NVRSMS platform:
- Light/white theme with crisp modern typography, glassmorphism accents, and refined color tokens.
- Complete typed API client (`src/api/client.ts`, `src/api/types.ts`) with automatic Bearer token injection, automatic 401 retry with refresh token rotation, and typed error handling.
- Authentication & RBAC Context (`src/context/AuthContext.tsx`) with login, TOTP 2FA flow, logout, token renewal, permission evaluation (`hasPermission`), and real-time permission sync.
- Toast notification system (`src/context/ToastContext.tsx`) for non-blocking feedback.
- Application Navigation Shell (`src/components/layout/`):
  - `Navbar.tsx`: Top header with platform branding, active tenant badge, WebSocket live status indicator, and user profile dropdown with TOTP status and logout.
  - `Sidebar.tsx`: Collapsible navigation sidebar linking to Dashboard, Live Monitor, Locations, Devices, Agents, Users, Roles, Audit Logs, and Settings.
- Route Protection & Guards:
  - `ProtectedRoute`: Redirects unauthenticated users to `/login`.
  - `PermissionRoute`: Evaluates required permissions and renders polished 403 fallback if unauthorized.
  - `LoginPage.tsx`: Premium login view with quick-fill demo roles (Super Admin, Operator, Auditor), animated transitions, and 2FA input modal.
- Automated testing suite verifying AuthContext, API client refresh interceptor, route guards, and component rendering.

### Files to Create / Modify

#### Design System & Tokens
- `frontend/src/index.css` — Modern design system tokens, CSS custom properties (colors, shadows, radiuses, transitions), reset, and utility classes.
- `frontend/src/App.css` — Layout grid, sidebar/navbar styling, animations.

#### API Layer & TypeScript Types
- `frontend/src/api/types.ts` — Full TypeScript interfaces matching Hub Backend Pydantic schemas:
  - `User`, `Tenant`, `Role`, `Permission`, `UserScope`
  - `Location`, `Province`, `City`, `Area`, `Site`
  - `NVR`, `Camera`, `StreamSession`, `Agent`, `AuditLog`
  - `LoginRequest`, `TokenResponse`, `MeResponse`
- `frontend/src/api/client.ts` — Typed fetch wrapper with:
  - Base URL configuration (`/api/v1`)
  - Request interceptor injecting `Authorization: Bearer <token>`
  - Response interceptor handling 401 with queued refresh token rotation
  - Standardized error classes (`ApiError`)

#### Contexts & State Management
- `frontend/src/context/AuthContext.tsx` — Authentication state, login, logout, profile fetching, TOTP handling, and `hasPermission(code)` helper.
- `frontend/src/context/ToastContext.tsx` — Global toast notification manager.

#### Components & Layout
- `frontend/src/components/layout/Navbar.tsx` — Top navbar with brand, tenant badge, live status, and user avatar dropdown.
- `frontend/src/components/layout/Sidebar.tsx` — Collapsible sidebar navigation.
- `frontend/src/components/layout/AppLayout.tsx` — Shell combining Navbar, Sidebar, and content `<Outlet />`.
- `frontend/src/components/common/Toast.tsx` — Animated toast alerts.
- `frontend/src/components/common/LoadingSpinner.tsx` — Clean SVG loading spinner.
- `frontend/src/components/common/AccessDenied.tsx` — 403 Forbidden feedback card.

#### Pages & Views
- `frontend/src/pages/LoginPage.tsx` — Login view with TOTP support and quick-fill demo accounts.
- `frontend/src/pages/DashboardPage.tsx` — Foundation dashboard view.
- `frontend/src/pages/NotFoundPage.tsx` — 404 handler.

#### Routing & Entry Point
- `frontend/src/router/routes.tsx` — Route configuration with `ProtectedRoute` and `PermissionRoute`.
- `frontend/src/App.tsx` — App root wrapping providers (`ToastProvider`, `AuthProvider`, `RouterProvider`).

#### Tests
- `frontend/src/tests/auth.test.tsx` — AuthContext login, logout, and permission checks.
- `frontend/src/tests/client.test.ts` — API client authentication header injection and error handling.
- `frontend/src/tests/navigation.test.tsx` — Sidebar and Navbar navigation and tenant display.
- `frontend/src/tests/guards.test.tsx` — ProtectedRoute and PermissionRoute tests.

### Gate Checklist
- [ ] Design system tokens and styles render clean, modern UI.
- [ ] Typed API client manages token storage and handles 401 refresh seamlessly.
- [ ] AuthContext provides reactive authentication, user profile, and `hasPermission` checks.
- [ ] Navbar displays user details, tenant tag, and active connection status.
- [ ] Sidebar highlights current route and allows navigation.
- [ ] ProtectedRoute blocks unauthorized access and redirects to `/login`.
- [ ] PermissionRoute displays 403 card when permission is revoked.
- [ ] Unit tests pass with >=80% coverage on frontend core modules.
- [ ] `npm run lint` and `npm test -- --run` execute with zero errors.
