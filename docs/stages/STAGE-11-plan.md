# CCTV Hub & Agent Platform — Stage 11 Plan

## Stage: Frontend Live Monitor and Operational Dashboard

### Objective
Build the real-time surveillance operations core and comprehensive monitoring dashboard:
1. **Multi-Camera Live Monitor Grid (`LiveMonitorPage.tsx`, `VideoCell.tsx`)**:
   - Configurable grid view modes: 1x1, 2x2 (quad), 3x3, 4x4 (16 cells).
   - Camera Selector Sidebar: searchable location/site tree listing online cameras.
   - Click/assign camera to active grid cell.
   - Real-time VideoCell player:
     - WebRTC/MSE stream token acquisition (`POST /api/v1/streams/request-token`).
     - Stream quality toggle: Main Stream (1080p) vs Sub Stream (adaptive low-bandwidth).
     - Camera info overlay: Channel number, camera name, live latency (ms), bitrate (kbps), FPS.
     - Controls: Mute/Unmute, Fullscreen, Snapshot frame capture, Close/Release stream.
     - Automatic viewer session cleanup on cell close to honour Hub 15s grace period.
2. **Operational Dashboard (`DashboardPage.tsx`)**:
   - Real-time metrics: Connected Edge Agents, Active Video Pipelines, Online Cameras, Storage Health, Cluster Uptime.
   - System Telemetry graphs/gauges.
   - Recent Security & Operational Event Feed (`/api/v1/audit`).
   - Quick Action Shortcuts.
3. **Audit Trail Module (`AuditPage.tsx`)**:
   - Filterable tabular view of system mutations, authentication events, lockout incidents, and stream sessions.
4. **Disaster Recovery & Settings Portal (`SettingsPage.tsx`)**:
   - Encrypted backup trigger button (`/api/v1/backup/create`).
   - Scratch restore integrity verification report.
   - Retention pruning policy viewer.
5. **Comprehensive Vitest Suite**:
   - Unit tests for LiveMonitor grid switching, VideoCell quality toggle, Dashboard metrics, and Audit table.

### Files to Create / Modify
- `frontend/src/components/streaming/VideoCell.tsx`
- `frontend/src/pages/LiveMonitorPage.tsx`
- `frontend/src/pages/DashboardPage.tsx`
- `frontend/src/pages/AuditPage.tsx`
- `frontend/src/pages/SettingsPage.tsx`
- `frontend/src/tests/live_monitor.test.tsx`
- `frontend/src/tests/dashboard.test.tsx`
- `frontend/src/tests/audit_settings.test.tsx`

### Gate Checklist
- [ ] Live Monitor supports 1x1, 2x2, 3x3, 4x4 grid layouts.
- [ ] Cameras can be assigned to grid cells from the location hierarchy.
- [ ] VideoCell supports Main vs Sub stream toggle, snapshot, and viewer release.
- [ ] Dashboard displays live telemetry metrics and audit event feed.
- [ ] Audit page filters events by action and resource type.
- [ ] Settings page triggers encrypted backup and displays DR status.
- [ ] All unit tests pass with zero failures.
- [ ] `npm run lint` and `npm run build` execute cleanly.
