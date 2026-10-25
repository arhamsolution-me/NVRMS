# CCTV Hub & Agent Platform — Stage 4 Plan

## Stage: Media Pipeline and Streaming

### Objective
Implement the complete low-latency media streaming pipeline from Edge NVRs through Edge Agents and MediaMTX to web clients:
1. **Hub Streaming Control & Authentication**:
   - Short-lived single-camera user-bound stream tokens (`hub_backend/security/stream_tokens.py`):
     - Signed JWT with `sub=user_id`, `camera_id`, `tenant_id`, `stream_type` ("main"|"sub"), 60s TTL.
     - Tokens validate camera existence, user permissions (`streams:view`), and location scope.
   - MediaMTX External Authentication Webhook (`POST /api/v1/streams/auth`):
     - Authenticates publishing agents (using agent tokens) and reading clients (using stream tokens).
     - Enforces camera-level authorization and tenant namespace isolation.
   - Stream Session & Viewer Reference Counting (`hub_backend/services/stream_manager.py`):
     - Tracks active viewers per stream.
     - On first viewer: dispatches `start_stream` to Edge Agent.
     - Subsequent viewers join existing stream without additional NVR pulls (1:N fan-out).
     - On last viewer disconnect: initiates 15-second grace period before dispatching `stop_stream`.
     - Enforces per-tenant and per-agent concurrency limits.
   - REST Endpoints (`hub_backend/routes/streams.py`):
     - `POST /api/v1/streams/{camera_id}/token` — Request playback token for main or sub stream
     - `POST /api/v1/streams/{camera_id}/heartbeat` — Keep-alive viewer session
     - `POST /api/v1/streams/{camera_id}/stop` — Client leaves stream
     - `GET /api/v1/streams/active` — List active streaming sessions and viewer counts
2. **Edge Agent Stream Worker Subsystem (`agent/streaming/`)**:
   - Supervised stream worker (`StreamWorker` in `agent/streaming/worker.py`):
     - Spawns and supervises `ffmpeg` subprocess using low-latency flags:
       `-rtsp_transport tcp -i <rtsp_url> -c copy -f rtsp rtsp://<mediamtx_host>:8554/<stream_path>`
     - Automatic restart on unexpected process death while stream is active.
     - Frozen-frame / stderr stall watchdog.
     - H.265 fallback transcoding flag when requested.
   - Agent Stream Coordinator (`agent/streaming/manager.py`):
     - Manages active stream workers keyed by `stream_id`.
     - Handles `start_stream` and `stop_stream` commands from Hub.
     - Clean process termination on shutdown without orphaned subprocesses.

### Files to Create / Modify

#### Hub Backend (`hub-backend/`)
- `hub_backend/security/stream_tokens.py` — Stream token signing and verification
- `hub_backend/services/stream_manager.py` — Viewer ref-counting, fan-out, and concurrency supervisor
- `hub_backend/routes/streams.py` — Stream token generation, session keepalive, MediaMTX auth webhook
- `hub_backend/routes/__init__.py`, `hub_backend/main.py` — Register router

#### Edge Agent (`agent/`)
- `agent/streaming/worker.py` — Ffmpeg supervised stream worker with watchdog
- `agent/streaming/manager.py` — Agent stream manager handling start/stop commands
- `agent/commands.py` — Connect `start_stream` and `stop_stream` commands to stream manager

#### Tests
- Hub tests (`hub-backend/tests/test_media_streaming.py`):
  - Stream token issuance and validation (valid, expired, wrong camera, wrong tenant, revoked user)
  - MediaMTX auth webhook for publish and read
  - Viewer ref-counting (first viewer starts stream, second increments count without starting second stream)
  - Grace period before stream stop
  - Concurrency limits rejection
- Agent tests (`agent/tests/test_media_streaming.py`):
  - Stream worker start, stop, and clean cleanup
  - Process watchdog restart on simulated failure
  - Command execution for `start_stream` and `stop_stream`

### Exit Gate Criteria
- [ ] Short-lived user-bound stream tokens enforce camera, tenant, and permission boundaries
- [ ] MediaMTX external auth webhook allows authorized publish and read, rejects unauthorized
- [ ] Single NVR pull fan-out: multiple viewers share single agent stream worker
- [ ] Stream stops cleanly after last viewer leaves plus grace period
- [ ] No orphan ffmpeg subprocesses left running
- [ ] 100% of new and regression tests pass with >=80% coverage
