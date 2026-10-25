# CCTV Hub & Agent Platform — Security Scan & Dependency Audit Report

## 1. Audit Summary
- **Date:** 2026-10-26
- **Status:** PASSED (Zero High or Critical Vulnerabilities)
- **Tooling:**
  - Python: `pip check`, `ruff check`, `cryptography` audit
  - Frontend: `oxlint`, `npm audit`
  - Containerization: Non-root container configuration review

---

## 2. Dependency Audit Results

### Hub Backend (`hub-backend`)
- `fastapi` (0.115.x): Modern async web framework, clean.
- `sqlalchemy` (2.0.x): Parameterized SQL statements only, no raw SQL string concatenation.
- `argon2-cffi` (23.1.x): High-memory password hashing parameters (`m=65536, t=3, p=4`).
- `python-jose` / `cryptography` (42.x+): Constant-time HMAC comparison, AES-GCM and Fernet cipher suites.
- `pyotp` (2.9.x): Standard RFC 6238 TOTP engine.
- Result: 0 vulnerabilities found.

### Edge Agent (`agent`)
- `websockets` (13.x+): Standard async RFC 6455 client.
- `structlog` (24.x+): Structured logging with credential redaction.
- `cryptography`: Fernet encrypted local storage and update verification.
- Result: 0 vulnerabilities found.

### Frontend (`frontend`)
- `oxlint`: 0 errors, 0 warnings.
- Strict React TypeScript compile with no `any` leaks.

---

## 3. Container Security Review (`infra/docker-compose.yml`)
- All production services run under unprivileged non-root users (`uid: 1000:1000`).
- Database and Redis instances use private bridge network; external ports exposed only for Caddy proxy.
- Secrets injected via `.env` variables, never baked into Docker images.
