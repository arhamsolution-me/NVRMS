# CCTV Hub & Agent Platform — Stage 5 Plan

## Stage: Resilience Layer

### Objective
Implement the complete failure matrix behaviors across Hub and Edge Agent to ensure the platform survives network drops, disconnections, process deaths, authentication revocations, low uplink bandwidth, disk exhaustion, clock skew, and failed software updates.

### Failure Matrix Behaviors (Section 12 of System Spec)

| # | Failure Mode | Component | Resilience Mechanism | Recovery Behavior |
|---|--------------|-----------|----------------------|-------------------|
| 1 | Hub connection loss / Network flap | Agent `client.py` | Exponential backoff with full jitter (1s to 60s) | Reconnects without crashing; resumes heartbeats |
| 2 | State drift on reconnection | Agent & Hub | Bidirectional state reconciliation on WSS connect | Agent reports active streams; Hub stops orphans and restarts missing streams |
| 3 | Process crash / ffmpeg death | Agent `StreamWorker` | Process supervisor with restart limit (max 5 restarts in 60s) | Automatically restarts ffmpeg; marks error if crash-looping |
| 4 | Frozen stream / Stalled frames | Agent `StreamWorker` | Stream watchdog monitoring process stdout/stderr activity | Kills stalled process and triggers supervisor restart |
| 5 | Auth failure / Credential revocation | Agent `client.py` | Retry-storm prevention on 4001/4003/401/403 | Enters long backoff (up to 300s) instead of tight loop; avoids thundering herd |
| 6 | Low uplink bandwidth / congestion | Agent & Hub | Adaptive stream selector (main -> sub fallback) | Downgrades from main to sub stream when uplink degrades |
| 7 | Disk exhaustion / Log accumulation | Agent `disk_monitor.py` | Disk threshold monitor & bounded FIFO log rotation | Prunes oldest log files when free space < safety margin or disk > 90% |
| 8 | Corrupted or failed self-update | Agent `updater.py` | Cryptographic signature verification & atomic rollback | Validates SHA-256 & signature; creates backup; rolls back if boot/health fails |
| 9 | Hardware clock skew / RTC drift | Agent `time_sync.py` | Hub timestamp offset compensation | Detects clock drift > 15s; calculates offset; compensates timestamps |

---

### Components to Build

#### 1. Agent Resilience Modules (`agent/resilience/`)
- `agent/resilience/time_sync.py`:
  - `TimeSyncManager`: Compares Agent local UTC clock with Hub server UTC timestamp.
  - Computes `clock_skew_seconds`. If `|drift| > 15s`, logs warning and adjusts outgoing timestamps.
- `agent/resilience/disk_monitor.py`:
  - `DiskMonitor`: Checks disk usage on log/data partition.
  - Automatically triggers log rotation and deletes oldest `.log` files when free space drops below threshold.
- `agent/resilience/updater.py`:
  - `AgentUpdater`: Handles self-update packages.
  - Verifies SHA-256 checksum and Ed25519/HMAC signature.
  - Atomically stages update, creates backup, and executes rollback if update verification fails.
- `agent/resilience/network_monitor.py`:
  - Monitors packet drops / stream latency.
  - Recommends adaptive degradation (`main` -> `sub`).

#### 2. Agent Enhancements (`agent/`)
- `agent/client.py`:
  - Integrate retry-storm prevention: if Hub returns 4001, 4003, or invalid token, agent enters prolonged backoff (up to 300s) and does not hammer Hub.
  - In `reconcile_state`: send active streams list on handshake so Hub can reconcile.
- `agent/streaming/worker.py`:
  - Enhanced watchdog with crash-loop backoff (max 5 crashes in 60s) and timeout watchdog on process stalls.
- `agent/commands.py`:
  - Wire `reconcile_state`, `check_disk`, `sync_time`, `apply_update` commands.

#### 3. Hub Backend Resilience Enhancements (`hub-backend/`)
- `hub_backend/services/agent_manager.py` & `hub_backend/routes/agent_ws.py`:
  - On agent connection, execute reconciliation:
    - Compare `agent.reported_active_streams` with `stream_manager.active_streams` for that agent.
    - If agent is streaming something no viewer is watching, send `stop_stream`.
    - If Hub has viewers for a stream the agent isn't publishing, re-issue `start_stream`.
- `hub_backend/services/stream_manager.py`:
  - Adaptive degradation logic: on agent low-uplink signal, switch stream to sub-stream.

---

### Automated Test Plan (`agent/tests/test_resilience.py` and `hub-backend/tests/test_resilience.py`)
1. **test_network_reconnect_backoff_and_jitter**: Verify agent survives connection drops and backoff increases with jitter bounds.
2. **test_state_reconciliation_stops_orphaned_streams**: Agent reports stream X, but Hub has no viewers; Hub commands agent to stop stream X.
3. **test_state_reconciliation_restarts_missing_streams**: Hub has active viewers for stream Y, but agent reconnected without stream Y; Hub re-issues start_stream.
4. **test_stream_worker_supervisor_auto_restart**: Kill ffmpeg process; worker automatically restarts up to threshold.
5. **test_stream_worker_crash_loop_protection**: Fast consecutive crashes trip circuit breaker and stop restart loop.
6. **test_stream_watchdog_detects_stall**: Stalled output triggers worker termination.
7. **test_retry_storm_prevention_on_auth_rejection**: 4001/4003 or invalid credentials triggers long exponential delay, preventing tight-loop storm.
8. **test_adaptive_bitrate_substream_fallback**: Simulating low uplink triggers fallback to sub stream.
9. **test_disk_log_rotation_and_cleanup**: Simulating disk usage trigger rotates logs and prunes oldest log files.
10. **test_self_update_signature_verification_and_rollback**:
    - Valid signature succeeds.
    - Tampered package or invalid signature is rejected.
    - Simulated boot failure triggers rollback to backup.
11. **test_time_drift_detection_and_compensation**: Clock drift > 15s is detected and compensated in timestamps.

---

### Exit Gate Criteria
- [ ] Every row of the failure matrix (1-9) has an automated passing test
- [ ] Reconnection with jitter and backoff proven
- [ ] State reconciliation cleans orphaned streams and restores missing streams
- [ ] Process supervisor and watchdog prevent orphan/hung processes
- [ ] Auth rejection enters backoff freeze preventing retry storms
- [ ] Disk monitor prunes bounded log FIFO
- [ ] Signature-verified updater rolls back on failed verification
- [ ] Time drift > 15s is detected and compensated
- [ ] 100% of all tests pass with zero regressions
