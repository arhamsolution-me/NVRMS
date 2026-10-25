# CCTV Hub & Agent Platform — Stage 8 Plan

## Stage: Observability

### Objective
Implement enterprise monitoring, Prometheus metrics exposition, component health diagnostics, alerting rules, Grafana dashboard visualization, and a secure Edge Agent diagnostics bundle with automated credential redaction:
1. **Prometheus Metrics Engine (`hub_backend/observability/metrics.py`)**:
   - `GET /metrics` Prometheus endpoint exposing:
     - `http_requests_total{method, path, status}`
     - `http_request_duration_seconds{method, path}`
     - `agents_connected_total`
     - `active_streams_total`
     - `active_stream_viewers_total`
     - `nvr_probe_operations_total{status}`
     - `dr_restore_verifications_total{status}`
2. **Deep Component Health Endpoint (`/health`)**:
   - Reports overall status plus individual subsystem status:
     - `database`: PostgreSQL / SQLite ping and latency
     - `redis`: Redis ping and latency
     - `agents`: count of online vs offline agents
     - `streams`: active streaming session count
3. **Alerting Rules Definition (`infra/monitoring/alerts.yml`)**:
   - Prometheus Alertmanager rules:
     - `AgentOffline`: Agent unresponsive > 90 seconds
     - `StreamWorkerFailed`: Stream restart count > 3 in 5 minutes
     - `DRRestoreFailed`: Restore verification failure
     - `LowDiskSpace`: Edge/Hub disk space < 10%
     - `HighAuthFailureRate`: 401/403 rate > 10 req/s
4. **Grafana Dashboard JSON (`infra/monitoring/grafana-dashboard.json`)**:
   - Dashboard with panels for HTTP traffic, latency percentiles (p50, p95, p99), active agents, live stream viewers, NVR status, and system errors.
5. **Edge Agent Diagnostics Bundle (`agent/diagnostics.py`)**:
   - Generates a complete troubleshooting bundle:
     - System info (OS, CPU, memory, uptime)
     - Disk stats (`shutil.disk_usage`)
     - Active streams list and recent stderr tail
     - Reachability diagnostics
     - Sanitized config and storage metadata
     - Strict regex and token redaction: guarantees passwords, tokens, private keys, and RTSP credentials never leak (`***REDACTED***`).

---

### Files to Create / Modify

#### Hub Backend
- `hub_backend/observability/metrics.py` — Prometheus metrics registry and exposition
- `hub_backend/routes/health.py` — Deep subsystem health check
- `hub_backend/main.py` — Mount `/metrics` endpoint

#### Edge Agent
- `agent/diagnostics.py` — Diagnostics collection and credential redaction engine
- `agent/commands.py` — Wire `get_diagnostics` command

#### Infrastructure & Monitoring
- `infra/monitoring/alerts.yml` — Prometheus Alertmanager rules
- `infra/monitoring/grafana-dashboard.json` — Grafana dashboard specification

#### Tests
- Hub Observability Tests (`hub-backend/tests/test_observability.py`):
  - `GET /metrics` returns valid Prometheus formatted metrics
  - Subsystem health checks report operational components
  - Simulated database or redis degradation reflects in `/health`
- Agent Observability Tests (`agent/tests/test_observability.py`):
  - Diagnostics bundle collection succeeds
  - Credential redaction removes all passwords, tokens, and authorization credentials
  - Secret scanner confirms zero plaintext secrets in bundle

---

### Exit Gate Criteria
- [ ] `/metrics` endpoint exposes Prometheus counters, gauges, and histograms
- [ ] `/health` endpoint exposes deep component checks (database, redis, agents, streams)
- [ ] Prometheus alert rules (`infra/monitoring/alerts.yml`) defined and validated
- [ ] Grafana dashboard JSON (`infra/monitoring/grafana-dashboard.json`) valid
- [ ] Edge diagnostics bundle strips all secrets and credentials with 100% reliability
- [ ] 100% of all tests pass with zero regressions
