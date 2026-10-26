# Jenkins CI Local Infrastructure Setup & Verification Evidence

## 1. Overview
The Jenkins CI controller and build environment for NVRSMS is fully containerized, reproducible, and defined entirely as code.

- **Controller Base Image:** `jenkins/jenkins:lts-jdk17` (v2.541.3)
- **Configuration as Code:** `infra/jenkins/casc.yaml`
- **Compose Definition:** `infra/jenkins/docker-compose.jenkins.yml`
- **Build Agent Image:** `nvrsms-build-agent:1.0.0` (`infra/jenkins/Dockerfile`)
- **Plugin Management:** Pre-baked via `jenkins-plugin-cli` (`infra/jenkins/plugins.txt`)
- **Web UI & API Endpoint:** `http://localhost:8080` / `http://127.0.0.1:8080`
- **Agent Tunnel Port:** `50000`

---

## 2. Pinned Plugins Verified
The following plugins are pre-installed into the controller image with no runtime installation delays or external dependency risks:
1. `configuration-as-code` (CasC)
2. `git` & `git-client`
3. `workflow-aggregator` (Declarative Pipelines)
4. `docker-workflow` (Docker agent execution)
5. `junit` (JUnit XML reporting)
6. `htmlpublisher` (HTML coverage & security report publishing)
7. `coverage` (Cobertura / coverage visualization)
8. `timestamper` (Timestamps in logs)
9. `ws-cleanup` (Workspace cleanup post-build)
10. `credentials-binding` (Masked secret injection)
11. `build-timeout` (Global and stage timeouts)
12. `pipeline-stage-view` (Visual stage status)
13. `job-dsl` (Automated pipeline seed jobs)
14. `ansicolor` (ANSI console color formatting)

---

## 3. Toolchain in `nvrsms-build-agent:1.0.0`
The pinned build agent image was built and verified with the following exact versions:

| Tool | Version / Command Output | Purpose |
|---|---|---|
| **Python** | `Python 3.12.3` | Backend, tests, security scanners |
| **Node.js** | `v22.23.4` (npm 10.9.2) | Frontend build & test, Playwright |
| **Go** | `go version go1.22.2 linux/amd64` | Agent / Go tooling |
| **Docker CLI** | `Docker version 29.9.2, build a82e528` | Container orchestration |
| **Gitleaks** | `8.30.1` | Git history secret scanning |
| **Trivy** | `Version: 0.76.1` | Container & filesystem vulnerability scanning |
| **Hadolint** | `Haskell Dockerfile Linter 2.12.0` | Dockerfile static analysis |
| **Semgrep** | `1.90.0` | SAST code scanning |
| **Bandit** | `bandit 1.7.10` | Python AST security analysis |
| **Pip-audit** | `pip-audit 2.7.3` | Python dependency CVE scanner |
| **Ruff** | `ruff 0.8.0` | Python linter and formatter |
| **Mypy** | `mypy 1.13.0` | Static type checker |
| **Black** | `black 24.10.0` | Python code formatter check |
| **Pytest** | `pytest 9.1.1` | Unit & integration test runner |
| **Tshark** | `TShark (Wireshark) 4.2.2` | Stream packet capture & entropy validation |

---

## 4. Verification Evidence

### 4.1. Jenkins Controller UI & Authentication
- **Endpoint:** `http://127.0.0.1:8080/login` -> HTTP 200 OK
- **Crumb Issuer Check:**
```json
{
  "_class": "hudson.security.csrf.DefaultCrumbIssuer",
  "crumb": "1a38d2c765aa0cd337d3e3f63d59d8e84f0be3f035f5dec1788dd1e4b53ef434",
  "crumbRequestField": "Jenkins-Crumb"
}
```
- **Controller API Query:**
```json
{
  "_class": "hudson.model.Hudson",
  "assignedLabels": [{"name": "built-in"}],
  "mode": "NORMAL",
  "numExecutors": 4,
  "description": "NVRSMS Platform CI/CD — Automated Local Jenkins Controller"
}
```

### 4.2. Seed Jobs Created Automatically by CasC
```json
[
  {"name": "nvrsms-pipeline", "url": "http://localhost:8080/job/nvrsms-pipeline/", "color": "notbuilt"},
  {"name": "nvrsms-nightly", "url": "http://localhost:8080/job/nvrsms-nightly/", "color": "notbuilt"}
]
```

### 4.3. Build Agent Container Execution via Controller
Executed from the controller context into `nvrsms-build-agent:1.0.0` through `/var/run/docker.sock`:
```
Client: Docker Engine - Community
 Version:           29.9.2
 API version:       1.52 (downgraded from 1.56)
 Go version:        go1.26.10
 Git commit:        a82e528
 Built:             Tue Oct 20 18:44:40 2026
 OS/Arch:           linux/amd64
 Context:           default

Server:
 Engine:
  Version:          29.1.3
  API version:      1.52 (minimum version 1.44)
  Go version:       go1.24.13
  Git commit:       29.1.3-0ubuntu4.1
  Built:            Wed Apr 29 16:40:20 2026
  OS/Arch:          linux/amd64

Python 3.12.3
```

---

## 5. Security & Isolation Architecture
1. **No Anonymous Access:** Anonymous users cannot read or execute any job.
2. **CSRF Protection:** Enabled with CrumbIssuer.
3. **Least Privilege Agent Access:** Build agent runs as `jenkins` user with group access to docker socket only for required container management.
4. **Environment Secrets:** Secrets are read exclusively from environment variables (`.env`) and credentials binding.
