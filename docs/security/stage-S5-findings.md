# Stage S5: Authentication and API Hardening Findings

## 1. Executive Summary

Stage S5 audited and hardened authentication mechanisms, session lifecycles, and API boundary protections across the NVRSMS Hub platform. The audit verified:
1. Every route across all controllers enforces strict authorization dependencies, with only documented public endpoints explicitly permitted.
2. Robust password security policies enforcing Argon2id hashing, 12+ character complexity, and rejection of known breached credentials.
3. Constant-time dummy verification on nonexistent accounts to defeat email enumeration timing attacks.
4. Active session tracking with remote per-session and all-session revocation capabilities.
5. Defense-in-depth security headers including HSTS with preload, restrictive Content-Security-Policy, anti-framing, and request body size caps.

---

## 2. Findings and Remediation

### Finding S5-1: Route Authorization Gap Risk (Fixed)
- **Vulnerability**: Without automated verification, newly added routes could accidentally omit authentication dependencies (`require_permission` or `get_current_user`), exposing internal resources.
- **Remediation**: Implemented `test_route_enumeration_all_routes_protected` which scans the FastAPI route table dynamically. Any route without an explicit authorization dependency or membership in `public_allowlist` causes test failure.
- **Evidence**: Verified all registered routes require authorization. Public allowlist strictly bounded to `/health`, `/metrics`, `/api/v1/auth/login`, `/api/v1/auth/refresh`, `/api/v1/agents/enrol`, and `/api/v1/streams/mediamtx/auth`.

### Finding S5-2: Weak and Breached Passwords Permitted (Fixed)
- **Vulnerability**: Passwords below 12 characters or present in known credential dumps could be chosen by users, creating vulnerability to credential stuffing.
- **Remediation**: Integrated `check_password_strength` into user creation (`POST /api/v1/users`) and update (`PUT /api/v1/users/{id}`). Rejects passwords shorter than 12 characters, missing character classes (uppercase, lowercase, number, special character), or matching common breached passwords (e.g., `Password123!`).
- **Evidence**: `test_password_policy_and_breached_password_detection` and `test_user_creation_rejects_weak_and_breached_passwords` pass.

### Finding S5-3: User Enumeration via Timing Side-Channels (Fixed)
- **Vulnerability**: If an email does not exist in the database, returning early without running Argon2id allows attackers to measure server response latency (~2ms vs ~80ms) and enumerate valid user accounts.
- **Remediation**: Added `dummy_verify()` which executes an Argon2id comparison against a precomputed dummy hash whenever a user lookup yields no record, equalizing execution timing.
- **Evidence**: `test_anti_enumeration_uniform_error_and_timing_defense` verified uniform `Invalid email or password` errors with indistinguishable response behaviors.

### Finding S5-4: Lack of Remote Session Management (Fixed)
- **Vulnerability**: Users had no mechanism to inspect active sessions or revoke compromised sessions remotely without changing passwords.
- **Remediation**: Added REST endpoints:
  - `GET /api/v1/auth/sessions`: Lists active, unexpired, non-revoked refresh token sessions for the caller.
  - `DELETE /api/v1/auth/sessions/{session_id}`: Revokes a specific session.
  - `DELETE /api/v1/auth/sessions`: Revokes all active sessions for the caller and clears session cookies.
- **Evidence**: `test_session_listing_and_remote_revocation` verified that revoking a session instantly invalidates subsequent refresh attempts (HTTP 401).

### Finding S5-5: Security Header Strengthening (Fixed)
- **Vulnerability**: HSTS lacked `preload` directive; Content-Security-Policy lacked explicit `script-src` and `connect-src` restrictions.
- **Remediation**: Updated `SecurityHeadersMiddleware` to output:
  - `Strict-Transport-Security: max-age=63072000; includeSubDomains; preload`
  - `Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self' wss: https:; frame-ancestors 'none'; object-src 'none'; base-uri 'self'; form-action 'self'`
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: DENY`
  - `Referrer-Policy: strict-origin-when-cross-origin`
  - `Permissions-Policy: geolocation=(), camera=(), microphone=(), payment=()`
  - 10MB payload size limit enforced via Content-Length checking (HTTP 413).
- **Evidence**: `test_security_headers_and_payload_limits` passed.

---

## 3. Automated Test Evidence Summary

| Test Case | Description | Result |
|---|---|---|
| `test_route_enumeration_all_routes_protected` | Full route table inspection for auth dependencies | PASSED |
| `test_unauthenticated_request_rejected_on_all_protected_endpoints` | Probe protected endpoints without token (HTTP 401/403) | PASSED |
| `test_password_policy_and_breached_password_detection` | Complexity checks & breach dictionary rejection | PASSED |
| `test_user_creation_rejects_weak_and_breached_passwords` | API enforcement of password policy | PASSED |
| `test_anti_enumeration_uniform_error_and_timing_defense` | Uniform login error message and dummy verification | PASSED |
| `test_session_listing_and_remote_revocation` | List active sessions, revoke single, revoke all | PASSED |
| `test_security_headers_and_payload_limits` | HSTS preload, CSP, nosniff, frame-ancestors, 413 limit | PASSED |

**Total Suite**: 7/7 Stage S5 tests passed. Full platform regression: 117/117 passed.
