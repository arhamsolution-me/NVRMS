# CCTV Hub & Agent Platform — Stage 3 Plan

## Stage: NVR Add by IP and Camera Discovery

### Objective
Implement end-to-end NVR discovery and onboarding by IP through the Edge Agent:
1. **Security & Diagnostics**:
   - SSRF protection: strictly enforce RFC 1918 private IP ranges by default (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `127.0.0.0/8` in dev/test); reject public IPs and cloud metadata (`169.254.169.254`).
   - TCP reachability diagnostics on target host and port before attempting authentication.
   - Authentication lockout guard: abort probe after 3 consecutive authentication failures to prevent NVR account freeze.
   - Robust URL-encoding of credentials with special characters (`@`, `:`, `/`, `#`, etc.).
   - Passwords stored **only on the agent** (encrypted via Fernet); Hub only stores NVR and Camera metadata without raw passwords.
2. **Channel & Stream Discovery**:
   - Data-driven vendor RTSP templates (`vendor_templates.json`) for Hikvision, Dahua, Uniview, Hanwha/Samsung, Axis, Xiongmai, and Generic RTSP.
   - Channel enumeration with main stream and sub stream path resolution.
   - Structured per-channel results: channel number, name, main RTSP URL, sub RTSP URL, codec (H.264/H.265), resolution, fps, status.
3. **Hub Multi-Tenant & Scoped Management**:
   - `NVR` and `Camera` models linked to `tenant_id` and `site_id`.
   - Uniqueness constraint on `(agent_id, ip, port)`.
   - Duplicate detection by serial number / MAC address.
   - Multi-agent isolation: the same IP (e.g. `192.168.1.100`) on two different agents is allowed and isolated.
   - REST endpoints: probe trigger, NVR CRUD, camera listing and scoping.

### Files to Create / Modify

#### Database & Models (`hub-backend/`)
- `hub-backend/hub_backend/models/nvr.py` — `NVR` model
- `hub-backend/hub_backend/models/camera.py` — `Camera` model
- `hub-backend/hub_backend/models/__init__.py` — Export `NVR`, `Camera`
- `hub-backend/alembic/versions/0004_nvr_and_camera_discovery.py` — Migration script

#### Hub Routes & Schemas (`hub-backend/`)
- `hub-backend/hub_backend/schemas/nvr.py` — Pydantic schemas for NVR & Camera
- `hub-backend/hub_backend/routes/nvrs.py` — NVR probe, creation, listing, detail, deletion
- `hub-backend/hub_backend/routes/cameras.py` — Camera listing and detail routes
- `hub-backend/hub_backend/routes/__init__.py` — Register routes

#### Agent Implementation (`agent/`)
- `agent/agent/discovery/ssrf.py` — SSRF IP validator
- `agent/agent/discovery/vendor_templates.json` — RTSP templates by vendor
- `agent/agent/discovery/nvr_probe.py` — Reachability check, template matcher, probe engine
- `agent/agent/commands.py` — Connect `probe_nvr` command to probe engine
- `agent/agent/storage.py` — Add encrypted NVR credential vault per NVR ID

#### Tests
- Hub tests (`hub-backend/tests/test_nvr_discovery.py`):
  - Probe command dispatch through agent manager
  - NVR creation and duplicate rejection on same agent
  - Same IP on two different agents allowed and isolated
  - Cross-site / cross-tenant scoping on NVRs and cameras
  - NVR and Camera CRUD operations
- Agent tests (`agent/tests/test_nvr_discovery.py`):
  - SSRF guard: public IP rejected, private IP allowed, cloud metadata blocked
  - Reachability check failure on closed port
  - Credential encoding with special characters
  - Lockout protection aborts on repeated failures
  - Multi-brand vendor template URL resolution

### Exit Gate Criteria
- [ ] SSRF guard rejects public IPs and AWS metadata
- [ ] Same IP on two different agents works with no data bleed
- [ ] Duplicate NVR on same agent rejected
- [ ] Structured channel results include main and sub streams
- [ ] NVR passwords stored only on agent encrypted, never plaintext in Hub DB
- [ ] 100% of new and regression tests pass with >=80% coverage
