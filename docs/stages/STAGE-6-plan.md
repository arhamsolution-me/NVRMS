# CCTV Hub & Agent Platform — Stage 6 Plan

## Stage: Security Hardening

### Objective
Harden the entire platform against attack vectors (IDOR, injection, brute-force, MITM, stream hijacking, secret compromise) and implement defense-in-depth:
1. **Security Headers & Transport Security Middleware (`hub_backend/security/headers.py`)**:
   - Strict-Transport-Security (HSTS) with `max-age=31536000; includeSubDomains`
   - `X-Content-Type-Options: nosniff`
   - `X-Frame-Options: DENY`
   - `Content-Security-Policy: default-src 'self'; frame-ancestors 'none'; object-src 'none'`
   - `Referrer-Policy: strict-origin-when-cross-origin`
   - `Permissions-Policy: geolocation=(), camera=(), microphone=()`
2. **CORS Allow-List & Request Body Limits**:
   - Environment-driven CORS origin matching (rejects wildcard `*` in production).
   - Maximum request payload size limit (e.g. 10MB) to prevent memory exhaustion via multipart/body floods.
3. **Rate Limiting & Brute-Force Safeguards (`hub_backend/security/rate_limit.py`)**:
   - Rate limiting on sensitive endpoints (`/api/v1/auth/login`, `/api/v1/auth/totp/verify`, `/api/v1/nvrs/probe`):
   - Sliding-window or token bucket rate limiter returning HTTP 429 Too Many Requests when limits are exceeded.
4. **Certificate Pinning on Edge Agent (`agent/security/pinning.py`)**:
   - Pinned SHA-256 certificate fingerprint verification for Hub WSS/HTTPS endpoints.
   - Rejects untrusted or MITM TLS certificates even if signed by an attacker CA installed in the edge OS trust store.
5. **Envelope Encryption for Stored Secrets (`hub_backend/security/envelope.py`)**:
   - Key Encrypting Key (KEK) + Data Encrypting Key (DEK) pattern using AES-256-GCM / Fernet.
   - Encrypts sensitive NVR credentials and agent secret material with rotated DEKs.
6. **Threat Model & Security Documentation (`docs/security/threat-model.md`)**:
   - Documented STRIDE threat model, trust boundaries, asset inventory, and mitigations.

---

### Files to Create / Modify

#### Hub Backend
- `hub_backend/security/headers.py` — Security headers middleware
- `hub_backend/security/rate_limit.py` — In-memory & Redis rate limiter with 429 responses
- `hub_backend/security/envelope.py` — KEK/DEK envelope encryption helper
- `hub_backend/main.py` — Register security headers and rate limiter middlewares

#### Edge Agent
- `agent/security/pinning.py` — TLS certificate SHA-256 fingerprint validator
- `agent/client.py` — Enforce certificate fingerprint check when configured

#### Documentation
- `docs/security/threat-model.md` — Complete STRIDE threat analysis and countermeasures
- `docs/security/scan-report.md` — Dependency audit and vulnerability review report

#### Tests
- Hub Security Tests (`hub-backend/tests/test_security_hardening.py`):
  - Security headers present on all responses (HSTS, CSP, nosniff, X-Frame-Options)
  - Rate limiting triggers HTTP 429 on login abuse
  - IDOR prevention: tenant A cannot view or mutate tenant B resources
  - Envelope encryption encrypts and decrypts with DEK/KEK correctly; tampered ciphertext fails
  - SQL injection and XSS payload rejection
- Agent Security Tests (`agent/tests/test_security_hardening.py`):
  - Certificate pinning matches valid fingerprint
  - Certificate pinning rejects mismatched/MITM certificate fingerprint

---

### Exit Gate Criteria
- [ ] All HTTP responses carry HSTS, CSP, X-Frame-Options, nosniff, and Referrer-Policy headers
- [ ] Rate limiter blocks brute force attempts with HTTP 429
- [ ] Cross-tenant IDOR attacks return 404 (concealed) or 403
- [ ] Certificate pinning in agent rejects mismatched TLS certificate fingerprints
- [ ] Envelope encryption protects stored credentials with DEK/KEK
- [ ] Threat model document (`docs/security/threat-model.md`) written
- [ ] 100% of security and regression tests pass
