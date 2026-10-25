# CCTV Hub & Agent Platform — Stage 10 Plan

## Stage: Frontend Admin Modules

### Objective
Implement the complete enterprise management modules for the NVRSMS frontend:
1. **Locations Hierarchy Manager (`LocationsPage.tsx`)**:
   - Interactive 4-level Tree: Province -> City -> Area -> Site.
   - Tree node expand/collapse, active node selection, and breadcrumbs.
   - Create/Edit/Delete modals with hierarchical parent scoping.
2. **Users & Scopes Management (`UsersPage.tsx`)**:
   - User table displaying email, display name, role, 2FA status, active toggle, and location scopes.
   - User modal for account creation and editing.
   - Scope assignment dialog: bind users to specific Province, City, Area, or Site.
   - Last super-admin protection validation in UI.
3. **Roles & RBAC Permission Matrix (`RolesPage.tsx`)**:
   - Dynamic Roles list and creation dialog.
   - Interactive Permission Matrix organized by functional domains (Cameras, Streams, Locations, Users, Roles, Audit, System/Backups).
   - Toggle checkboxes with instant state update and visual save indicator.
4. **NVR & Camera Management (`DevicesPage.tsx`)**:
   - NVR table with IP, vendor, assigned agent, status, and camera count.
   - "Add NVR" modal with SSRF-safe IP inputs, vendor templates (Hikvision, Dahua, Uniview, Generic RTSP), and credentials.
   - Live "Probe NVR" action triggering discovery via connected agent, showing channel count and discovered RTSP stream URLs.
   - Camera channel list per NVR with main/sub stream details and PTZ badges.
5. **Edge Agent Fleet (`AgentsPage.tsx`)**:
   - Agent table with connection status indicator, heartbeat timestamps, and version.
   - "Enrol Agent" dialog generating single-use enrolment codes with copy-to-clipboard.
   - Diagnostics modal displaying real-time system metrics, disk stats, time sync offset, and sanitized credentials.
6. **Automated Vitest Suite**:
   - Comprehensive component tests for Locations, Users, Roles, Devices, and Agents modules.

### Files to Create / Modify
- `frontend/src/pages/LocationsPage.tsx`
- `frontend/src/pages/UsersPage.tsx`
- `frontend/src/pages/RolesPage.tsx`
- `frontend/src/pages/DevicesPage.tsx`
- `frontend/src/pages/AgentsPage.tsx`
- `frontend/src/tests/locations.test.tsx`
- `frontend/src/tests/users.test.tsx`
- `frontend/src/tests/roles.test.tsx`
- `frontend/src/tests/devices.test.tsx`
- `frontend/src/tests/agents.test.tsx`

### Gate Checklist
- [ ] Locations tree enables traversing Province -> City -> Area -> Site.
- [ ] Users page supports user creation, role assignment, and location scoping.
- [ ] Roles page displays permission matrix with toggleable permissions.
- [ ] Devices page supports NVR onboarding and probe workflow.
- [ ] Agents page generates enrolment codes and renders fleet diagnostics.
- [ ] All unit tests pass with zero failures.
- [ ] `npm run lint` and `npm run build` execute cleanly.
