# CCTV Hub & Agent Platform — Stage 2 Plan

## Stage: Agent Enrolment and Control Channel

### Objective
Implement the secure agent management lifecycle and bi-directional real-time WebSocket control gateway between the Hub and Edge Agents:
1. Hub-side Agent Management:
   - Agent entity and enrolment token entity with single-use SHA-256 hashed codes (15-minute expiry).
   - Agent enrolment API (`/api/v1/agents/enrol-token`, `/api/v1/agents/enrol`).
   - Agent credential pair: unique `agent_id` + cryptographic bearer token / mTLS token pair.
   - Outbound WebSocket gateway `/ws/agent` with authentication, connection tracking, duplicate connection termination, and graceful shutdown.
   - Command envelope: `id` (UUID), `command` (whitelisted action), `payload`, `timestamp`, `timeout_seconds`, `idempotency_key`.
   - Command whitelist: `ping`, `get_status`, `probe_nvr`, `start_stream`, `stop_stream`, `reconcile_state`.
   - Agent heartbeat tracker with offline detection after 3 missed heartbeats (90 seconds).
   - Agent revocation and credential rotation APIs: revoking immediately terminates any live active WebSocket connection and rejects subsequent connection attempts.
2. Edge Agent Implementation (`agent/`):
   - Secure encrypted local storage (`Fernet` AES-CBC-HMAC derived from machine/local secret or secure key file) for storing agent ID, hub URL, and assigned credentials.
   - Autonomous enrolment workflow: agent uses enrolment code to authenticate, acquire credentials, and persist them securely.
   - Outbound WSS client with exponential backoff and jitter reconnection logic.
   - Periodic heartbeat runner (30s interval).
   - Command processor with whitelist validation, acknowledgement, result dispatch, and error handling.
   - State reconciliation: upon reconnection, agent reports current active streams and device snapshots to sync state with the hub.

### Files to Create / Modify

#### Database & Models (`hub_backend/models/`)
- `hub_backend/models/agent.py` — `Agent`, `AgentEnrolmentToken`
- `alembic/versions/0003_agent_enrolment.py` — Migration for agent tables

#### Hub Agent Routes & Services (`hub_backend/services/` & `hub_backend/routes/`)
- `hub_backend/services/agent_manager.py` — Active agent connection tracker, command dispatch, response waiter, revocation
- `hub_backend/routes/agents.py` — REST endpoints for agents: generate enrolment code, list, revoke, rotate credentials
- `hub_backend/routes/agent_ws.py` — WebSocket gateway `/ws/agent`

#### Agent Implementation (`agent/`)
- `agent/storage.py` — Encrypted credential storage using `cryptography.fernet.Fernet`
- `agent/client.py` — WSS connection client with backoff, jitter, heartbeat, and command execution
- `agent/commands.py` — Command dispatcher and whitelist handler

#### Tests
- Hub tests (`hub-backend/tests/test_agent_lifecycle.py`):
  - Generate enrolment code -> enrol agent -> credentials returned
  - Expired code rejected (400)
  - Reused code rejected (400)
  - Revoking an agent immediately drops live connection and blocks reconnect
  - Duplicate agent connection terminates old socket cleanly
  - Command dispatcher sends whitelisted commands, receives ack and result
  - Unknown/non-whitelisted command rejected with error envelope
  - Missed heartbeat triggers offline status
- Agent tests (`agent/tests/test_agent_client.py`):
  - Encrypted storage save/load/tamper check
  - Enrolment client flow
  - Heartbeat and reconnection backoff with jitter
  - Command execution and response packaging

### Exit Gate Criteria
- [ ] Agent enrols with single-use code; code cannot be reused or used after 15m
- [ ] Connected agent stays connected with 30s heartbeats
- [ ] Revoking an agent disconnects live WebSocket connection within 1 second and blocks reconnect
- [ ] Duplicate connection with same agent ID drops previous connection cleanly
- [ ] Non-whitelisted commands are rejected
- [ ] 100% of new and regression tests pass with >=80% coverage
