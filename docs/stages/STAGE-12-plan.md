# CCTV Hub & Agent Platform — Stage 12 Plan

## Stage: Integration, Load, Soak and Release

### Objective
Execute the final, authoritative platform verification stage:
1. **End-to-End Platform Integration Test Suite (`hub-backend/tests/test_integration_e2e.py`)**:
   - **Flow 1: Agent Enrolment to Stream Teardown**:
     - Generate single-use enrolment code on Hub.
     - Agent enrols, receives cryptographic agent token, saves to encrypted vault.
     - Agent connects outbound WSS, establishes session, exchanges heartbeat with time sync.
     - Hub dispatches NVR probe via Agent WSS -> parses multi-channel RTSP streams.
     - Hub onboards NVR and cameras with site association.
     - User requests stream playback token (signed JWT with 60s TTL).
     - MediaMTX auth webhook verifies agent publisher and user viewer.
     - Multi-viewer fan-out: second viewer joins existing stream (single worker pull).
     - Viewers disconnect -> 15s grace period triggers -> clean stop stream dispatched.
   - **Flow 2: Hierarchical Scoping & Multi-Tenant IDOR Guard**:
     - Hierarchy: Tenant A (Province -> City -> Area -> Site 1 & Site 2).
     - User scoped to Site 1 cannot view or probe NVRs on Site 2.
     - Tenant B attempts to access Tenant A agent, NVR, or camera -> receives concealed 404.
   - **Flow 3: Instantaneous Dynamic RBAC Toggle**:
     - Standard operator user requests camera streaming.
     - Administrator revokes `STREAMS_VIEW` permission from operator role.
     - Next immediate request by operator fails closed with HTTP 403 without token expiration delay.
     - Administrator re-grants permission -> next request succeeds immediately with HTTP 200.
   - **Flow 4: Disaster Recovery Verification**:
     - Live database populated with users, sites, NVRs, and cameras.
     - Encrypted authenticated backup triggered (`AES-128-CBC + HMAC-SHA256`).
     - Automated scratch database restore integrity verification executes, proving 100% record fidelity.
2. **Automated Soak & Load Testing Suite (`hub-backend/tests/test_soak_and_load.py`)**:
   - **Agent Heartbeat Soak**: Continuous simulated agent heartbeats over extended iterations validating memory stability, timestamp compensation, and Redis session tracking.
   - **Concurrent Stream Fan-Out Load**: Burst of concurrent simulated viewers against single camera channel verifying thread-safe reference counting, zero duplicate worker creation, and clean concurrency limits.
   - **Rate Limiter Soak & Recovery**: Sliding-window burst traffic against authentication and probe endpoints, proving 429 block and subsequent window expiry recovery.
3. **Comprehensive Platform Final Report (`docs/FINAL_REPORT.md`)**:
   - Complete technical overview of Hub Backend, Edge Agent, and Frontend modules.
   - Detailed Stage 0 through Stage 12 execution matrix.
   - Failure Matrix validation verification (Rows 1-9).
   - DR RTO and RPO validation.
   - Test metrics across backend, edge agent, and web frontend.
4. **Git Commit & Tag**:
   - Commit: `stage-12: Integration, Load, Soak and Release complete`
   - Tag: `stage-12-done`

### Gate Checklist
- [ ] End-to-end integration flows test pass with 100% success.
- [ ] Soak and load test suite passes under simulated concurrent traffic.
- [ ] Full regression across all existing Hub, Agent, and Frontend tests remains 100% green.
- [ ] `docs/FINAL_REPORT.md` written with exhaustive architecture, test results, and release notes.
- [ ] `docs/PROGRESS.md` updated with Stage 12 results.
- [ ] Git commit and tag `stage-12-done` created.
