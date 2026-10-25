# CCTV Hub & Agent Platform — Stage 0 Plan

## Stage: Foundation

### Objective
Bootstrap the entire repository structure, Docker Compose stack, Makefile, CI pipeline, config management, migration tooling, and logging so that every subsequent stage has a working foundation.

### Files to Create

#### Repository Root
- `README.md` — Setup guide
- `Makefile` — `up`, `down`, `test-all`, `lint`, `migrate`, `shell-hub`, `logs`
- `.env.example` — All required env vars with safe defaults
- `.gitignore`
- `.github/workflows/ci.yml` — CI pipeline (lint + test)

#### `/hub-backend`
- `pyproject.toml` — Poetry / pip dependencies, ruff + black config
- `hub_backend/main.py` — FastAPI app factory with health endpoint
- `hub_backend/config.py` — Pydantic Settings from env
- `hub_backend/db.py` — Async SQLAlchemy engine + session factory
- `hub_backend/logging_config.py` — Structlog structured JSON logging
- `alembic/` — Migration tooling
- `alembic/env.py`, `alembic.ini`
- `alembic/versions/0001_initial.py` — Empty initial migration (proves tooling works)
- `tests/__init__.py`, `tests/conftest.py` (Postgres+Redis test containers)
- `tests/test_health.py` — Health endpoint smoke test

#### `/agent`
- `pyproject.toml`
- `agent/main.py` — Placeholder main loop
- `agent/config.py` — Settings
- `agent/logging_config.py`

#### `/frontend`
- Vite + React + TypeScript scaffold (created via `npx`)
- `vite.config.ts`, `tsconfig.json` (strict)
- `eslint.config.js` + prettier config

#### `/media`
- `mediamtx.yml` — MediaMTX config for dev (RTSP, WHIP, external auth hook stub)

#### `/infra`
- `docker-compose.yml` — Postgres, Redis, MediaMTX, hub-backend, Nginx/Caddy reverse proxy
- `docker-compose.test.yml` — Testcontainers override for CI
- `Dockerfile.hub` — Hub backend Dockerfile (non-root)
- `Dockerfile.agent` — Agent Dockerfile (non-root)

#### `/docs`
- `docs/stages/STAGE-0-plan.md` (this file)
- `docs/PROGRESS.md`
- `docs/ASSUMPTIONS.md`

### Interfaces / Contracts
- `GET /health` → `{"status": "ok", "version": "0.1.0"}`
- Postgres: accessible at `postgres:5432` inside compose, `localhost:5432` from host
- Redis: `redis:6379`
- MediaMTX RTSP: `localhost:8554`, WebRTC (WHIP): `localhost:8889`

### Test List
1. `test_compose_healthy` — `docker compose ps` shows all services healthy
2. `test_health_endpoint` — `GET /health` returns 200 `{"status":"ok"}`
3. `test_migrations_apply` — `alembic upgrade head` exits 0
4. `test_migrations_rollback` — `alembic downgrade base` exits 0
5. `test_lint_hub` — `ruff check hub_backend/` exits 0
6. `test_lint_agent` — `ruff check agent/` exits 0

### Exit Gate Checklist
- [ ] `make up` → all compose services healthy
- [ ] `make test-all` → all tests pass
- [ ] `make lint` → no lint errors
- [ ] README explains setup
