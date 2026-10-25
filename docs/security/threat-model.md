# CCTV Hub & Edge Agent Platform — STRIDE Threat Model

## 1. System Overview & Trust Boundaries

The NVRSMS platform connects Edge Agents running in remote branch networks to a central multi-tenant Hub Backend and MediaMTX streaming server.

```
+─────────────────────────────────────────────────────────────+
|                    Edge Branch Network                      |
|  +--------------------+         +------------------------+  |
|  | Physical NVR / IPC |<---RTSP--|  Edge Agent            |  |
|  | (192.168.1.0/24)   |         |  - SSRF Guard          |  |
|  +--------------------+         |  - Fernet Cred Vault   |  |
|                                 |  - Cert Pinning        |  |
|                                 +-----------|------------+  |
+─────────────────────────────────────────────|───────────────+
                   Trust Boundary 1           | Outbound WSS / TLS
                                              v
+─────────────────────────────────────────────────────────────+
|                    Cloud / DMZ Network                      |
|                                                             |
|  +-------------------------+      +----------------------+  |
|  | Caddy Reverse Proxy     |----->| MediaMTX SFU         |  |
|  | (TLS 1.3 / HSTS / CSP)  |      | - Webhook Auth Check |  |
|  +------------|------------+      +----------------------+  |
|               |                               ^             |
|               v                               |             |
|  +-------------------------+                  |             |
|  | Hub Backend (FastAPI)   |------------------+             |
|  | - Envelope Encryption   |                                |
|  | - RBAC & Location Scope |                                |
|  | - Sliding Rate Limiting |                                |
|  +------------|------------+                                |
|               v                                             |
|  +-------------------------+                                |
|  | PostgreSQL 16 & Redis 7 |                                |
|  | - Multi-tenant schema   |                                |
|  +-------------------------+                                |
+─────────────────────────────────────────────────────────────+
                   Trust Boundary 2           ^
                                              | HTTPS / WebRTC
+─────────────────────────────────────────────|───────────────+
|                    Public Internet                          |
|  +-------------------------+                                |
|  | Web Browser Clients     |                                |
|  | (Operators & Viewers)   |                                |
|  +-------------------------+                                |
+─────────────────────────────────────────────────────────────+
```

---

## 2. Asset Inventory

| Asset | Description | Sensitivity | Protection Mechanism |
|-------|-------------|-------------|----------------------|
| **NVR Passwords** | Admin credentials to edge cameras | Critical | Stored encrypted locally on agent using Fernet; never stored in Hub DB |
| **Stream Tokens** | 60s single-camera viewing JWTs | High | User-bound, signed with HMAC-SHA256, verified by MediaMTX auth webhook |
| **Agent Auth Tokens**| Long-lived credentials for WSS | High | SHA-256 hashed in database; single-use enrolment codes (15m expiry) |
| **User Password Hashes** | Argon2id password hashes | Critical | Salted Argon2id with lockout after 5 consecutive failures |
| **Video Feeds** | Live RTSP/WebRTC CCTV streams | High | MediaMTX auth webhook requires valid user stream token matching path |
| **Audit Logs** | Immutable system event log | High | Append-only database table; records IP, correlation ID, and user |

---

## 3. STRIDE Threat Analysis & Mitigations

### 1. Spoofing (Identity)
- **Threat:** Attacker spoofs an Edge Agent to hijack command execution or access internal NVRs.
  - **Mitigation:** Mutual authentication via bearer agent tokens hashed with SHA-256; duplicate connection attempts drop the existing socket with code `4002`.
- **Threat:** Attacker impersonates the Hub using a rogue CA certificate (MITM).
  - **Mitigation:** Edge Agent enforces TLS certificate pinning (`agent/security/pinning.py`), comparing peer certificate fingerprints against pinned hashes.

### 2. Tampering (Data Integrity)
- **Threat:** Tampering with stream playback tokens to view unauthorized cameras.
  - **Mitigation:** Tokens are signed with server secret key and bind `user_id`, `camera_id`, `tenant_id`, and `stream_type`. MediaMTX webhook checks path equality against token claims.
- **Threat:** Tampering with Agent self-update packages.
  - **Mitigation:** Agent self-updater (`agent/resilience/updater.py`) verifies SHA-256 checksum and cryptographic HMAC/Ed25519 signature before staging, with automatic rollback.

### 3. Repudiation
- **Threat:** Malicious administrator disables cameras or deletes users without record.
  - **Mitigation:** Immutable audit logger (`hub_backend/services/audit.py`) records all mutations, security events, logins, and permission changes with timestamp, user ID, tenant ID, and IP address.

### 4. Information Disclosure
- **Threat:** Cross-tenant IDOR attack where Tenant A requests camera/agent details belonging to Tenant B.
  - **Mitigation:** Fail-closed tenant isolation. Queries filter strictly by `tenant_id`. Cross-tenant requests return HTTP 404 (concealed) rather than 403 to prevent enumeration.
- **Threat:** Data leakage via HTTP headers or browser caching.
  - **Mitigation:** Security headers middleware applies HSTS (`max-age=31536000`), `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, and strict CSP.

### 5. Denial of Service (DoS)
- **Threat:** Attacker floods login or probe endpoints to brute force credentials or exhaust Hub resources.
  - **Mitigation:** Sliding-window rate limiter (`hub_backend/security/rate_limit.py`) blocks requests exceeding limits with HTTP 429 Too Many Requests; 5-strike account lockout freezes user for 15 minutes.
- **Threat:** Large HTTP request payload crashes backend process.
  - **Mitigation:** Request payload limiter rejects bodies larger than 10MB with HTTP 413.

### 6. Elevation of Privilege
- **Threat:** User with "Viewer" role attempts to add NVRs or modify roles.
  - **Mitigation:** Strict `require_permission(code)` dependency checks versioned Redis permission cache; modifying role permissions invalidates cache and kicks unauthorized users on next request.
- **Threat:** Last remaining Super Admin is demoted or deleted.
  - **Mitigation:** Super Admin protection guard blocks deactivation, deletion, or role change of the final active Super Admin.

---

## 4. Residual Risks & Operational Recommendations
1. Rotate `ENCRYPTION_MASTER_KEY` every 12 months using envelope re-wrapping.
2. Maintain separate VLANs for CCTV cameras and corporate workstations.
3. Review audit trail weekly for failed authentication spikes.
