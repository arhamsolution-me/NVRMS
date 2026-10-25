# NVRSMS — Hub & Agent CCTV Platform

## Quick Start

### Prerequisites
- Docker Desktop ≥ 4.x (with Compose v2)
- Python 3.12+ (for running hub-backend outside Docker)
- Node.js 20+ (for frontend development)
- `make` (Git Bash / WSL on Windows, or native on Linux/macOS)

### 1. Clone and configure

```bash
git clone <repo>
cd NVRSMS
cp .env.example .env
# Edit .env and fill in secrets
```

### 2. Start the stack

```bash
make up
```

All services will be healthy within ~30 seconds.

### 3. Verify health

```bash
curl http://localhost:8000/health
# {"status":"ok","version":"0.1.0"}
```

### 4. Apply database migrations

```bash
make migrate
```

### 5. Run all tests

```bash
make test-all
```

### 6. Lint

```bash
make lint
```

---

## Repository Layout

```
/hub-backend   FastAPI backend (Python 3.12, SQLAlchemy async, Alembic)
/agent         Edge agent (Python, connects to hub via WSS)
/frontend      React 18 + TypeScript + Vite
/media         MediaMTX config and related scripts
/infra         docker-compose, Dockerfiles, backup scripts, monitoring
/docs          Specs, stages, progress, runbooks, security reports
/tests         E2E, load, security tests
```

## Architecture Overview

```
Browser  <--HTTPS/WebRTC-->  Nginx/Caddy  <-->  Hub Backend (FastAPI)
                                                      |         |
                                                  Postgres   Redis
                                                      |
                                             Control Channel (WSS)
                                                      |
                                                   Agent(s)
                                                      |
                                              NVR(s) via RTSP/ONVIF
                                                      |
                                                 MediaMTX SFU
```

## Services

| Service | Port | Description |
|---------|------|-------------|
| hub-backend | 8000 | FastAPI REST + WebSocket |
| postgres | 5432 | PostgreSQL 16 |
| redis | 6379 | Redis 7 |
| mediamtx | 8554/8889 | RTSP relay / WebRTC WHIP |
| proxy | 80/443 | Caddy reverse proxy |

## Environment Variables

See `.env.example` for all required variables.

## Agent Language

The edge agent is written in **Python 3.12** using asyncio. See `docs/ASSUMPTIONS.md` for rationale.

## NVR Simulator

In CI and development, a simulated NVR is provided by MediaMTX re-streaming an ffmpeg test pattern via RTSP. See `infra/docker-compose.yml` for the `nvr-sim` service.
