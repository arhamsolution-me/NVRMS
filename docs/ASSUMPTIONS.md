# Assumptions

This file records all design decisions made when specifications were ambiguous.

| # | Stage | Assumption | Reason |
|---|-------|-----------|--------|
| 1 | 0 | `hub-agent-nvr-build-prompt.md` and `hub-frontend-plan.md` spec files were not provided separately; all specification is derived from the staged autonomous build prompt itself | Files not present in workspace; user confirmed to proceed |
| 2 | 0 | Agent language chosen: **Python** (FastAPI-compatible, async, well-tested RTSP/ONVIF libraries) | Simpler hiring story, shared library ecosystem with hub backend |
| 3 | 0 | MediaMTX used as the RTSP/WHIP/WebRTC relay server | Best open-source candidate for SFU-lite RTSP→WebRTC |
| 4 | 0 | Simulated NVR: MediaMTX re-streaming an ffmpeg-generated test pattern via RTSP | No physical NVR available in CI environment |
| 5 | 0 | TLS in development uses self-signed certs via mkcert; production uses Let's Encrypt (Caddy) | Simplest zero-downtime TLS for both dev and prod |
| 6 | 0 | Database: PostgreSQL 16 with pgcrypto and uuid-ossp extensions | Stable, supports UUID, JSONB, row-level locking |
| 7 | 0 | Redis 7 used for cache, rate limiting, pub/sub (permission change events, WebSocket fan-out) | Standard choice for session/token cache and pub/sub |
| 8 | 0 | Frontend framework: Vite + React 18 + TypeScript strict | As specified in Stage 9 |
| 9 | 0 | CI: GitHub Actions (`.github/workflows/`) | Most common, free for OSS |
| 10 | 0 | Migration tooling: Alembic (Python) for hub-backend | Native to SQLAlchemy ecosystem |
