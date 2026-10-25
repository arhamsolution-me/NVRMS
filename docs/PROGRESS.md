# NVRSMS Platform — Build Progress

This file is appended after each completed stage.

---

## Stage 0: Foundation   [PASSED]
- Built:
  - Repository layout (`hub-backend`, `agent`, `frontend`, `media`, `infra`, `docs`, `tests`)
  - Docker Compose stack (`infra/docker-compose.yml`) with PostgreSQL 16, Redis 7, MediaMTX 1.9.1, NVR simulator (ffmpeg testsrc2 + drawtext timestamp), Hub Backend, and Caddy reverse proxy
  - Hub Backend scaffold: FastAPI app with correlation ID middleware, structured JSON/console logging with structlog, async SQLAlchemy engine + session factory, pydantic settings, Alembic async migration tooling
  - Edge Agent scaffold: Python 3.11 async architecture with config, structlog logging, and main entrypoint
  - Frontend scaffold: React 19 + TypeScript + Vite with Vitest, jsdom, oxlint
  - CI workflow (`.github/workflows/ci.yml`), Makefile, `.env.example`, `.gitignore`, `README.md`
- Tests:
  - Hub: 7/7 tests passing (health checks, correlation ID propagation, CORS headers, Alembic migrations apply and rollback)
  - Agent: 5/5 tests passing (config defaults, heartbeat interval, reconnect jitter limits, logging configuration)
  - Frontend: 2/2 tests passing (App component render, counter interactive button)
  - Coverage: 85% on hub-backend core modules
- Gate:
  - compose stack configuration: PASS (validated compose file with healthchecks on all services)
  - health endpoints respond: PASS (HTTP 200 `{"status":"ok","version":"0.1.0"}`)
  - migrations apply and roll back cleanly: PASS (`test_migrations_apply_and_rollback` green)
  - lint & formatting: PASS (ruff check/format clean on hub-backend and agent, oxlint clean on frontend)
  - README explains setup: PASS (detailed architecture, quick start, service list)
- Issues found and fixed:
  - Fixed `setuptools.backends.legacy:build` deprecated PEP 517 backend in `pyproject.toml` to standard `setuptools.build_meta`
  - Fixed pydantic settings validation in test fixtures by establishing test environment defaults before module import
  - Supported dual-engine initialization in `hub_backend/db.py` to allow SQLite tests in local environments without Docker while retaining PostgreSQL pool configuration for compose/production
  - Made initial migration dialect-safe for both PostgreSQL extensions and SQLite testing
- Assumptions made:
  - Agent language: Python 3.11+
  - Docker not locally installed on host Windows OS; local testing utilizes SQLite/aiosqlite and fakeredis test fixtures alongside complete docker-compose definitions for containerized environments
- Not verified on real hardware:
  - Physical NVR hardware (simulated via MediaMTX RTSP stream with drawtext PTS overlay)
- Known limitations:
  - None for foundation stage
- Commit/tag: stage-0-done
