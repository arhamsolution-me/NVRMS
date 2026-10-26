.PHONY: up down restart logs migrate migrate-down migrate-history \
        test-hub test-agent test-frontend test-unit test-integration test-e2e test-security test-all \
        lint lint-hub lint-agent lint-frontend typecheck typecheck-hub typecheck-agent typecheck-frontend \
        shell-hub shell-db build help \
        jenkins-up jenkins-down jenkins-logs jenkins-build

# ── Configuration ──────────────────────────────────────────
COMPOSE        := docker compose
COMPOSE_FILE   := infra/docker-compose.yml
JENKINS_COMPOSE:= infra/jenkins/docker-compose.jenkins.yml
HUB_DIR        := hub-backend
AGENT_DIR      := agent
FRONTEND_DIR   := frontend
PYTHON         := python3

# ── Stack Management ───────────────────────────────────────
up:
	$(COMPOSE) -f $(COMPOSE_FILE) up -d --build
	@echo "⏳ Waiting for services..."
	@sleep 5
	$(COMPOSE) -f $(COMPOSE_FILE) ps

down:
	$(COMPOSE) -f $(COMPOSE_FILE) down -v

restart:
	$(COMPOSE) -f $(COMPOSE_FILE) restart

logs:
	$(COMPOSE) -f $(COMPOSE_FILE) logs -f

# ── Local Jenkins Management ───────────────────────────────
jenkins-build:
	@echo "🔨 Building Jenkins agent image..."
	docker build -t nvrsms-build-agent:1.0.0 -t nvrsms-build-agent:latest -f infra/jenkins/Dockerfile infra/jenkins

jenkins-up:
	@echo "🚀 Starting Local Jenkins CI stack..."
	@bash infra/jenkins/scripts/jenkins-up.sh

jenkins-down:
	@echo "🛑 Stopping Local Jenkins CI stack..."
	@bash infra/jenkins/scripts/jenkins-down.sh

jenkins-logs:
	$(COMPOSE) -f $(JENKINS_COMPOSE) logs -f

# ── Database Migrations ────────────────────────────────────
migrate:
	@cd $(HUB_DIR) && alembic upgrade head

migrate-down:
	@cd $(HUB_DIR) && alembic downgrade base

migrate-history:
	@cd $(HUB_DIR) && alembic history --verbose

# ── Lint / Format ──────────────────────────────────────────
lint-hub:
	@cd $(HUB_DIR) && ruff check . && ruff format --check .

lint-agent:
	@cd $(AGENT_DIR) && ruff check . && ruff format --check .

lint-frontend:
	@cd $(FRONTEND_DIR) && npm run lint

lint: lint-hub lint-agent lint-frontend
	@echo "✅ Lint passed"

# ── Type Checking ──────────────────────────────────────────
typecheck-hub:
	@cd $(HUB_DIR) && mypy hub_backend

typecheck-agent:
	@cd $(AGENT_DIR) && mypy agent

typecheck-frontend:
	@cd $(FRONTEND_DIR) && npx tsc --noEmit

typecheck: typecheck-hub typecheck-agent typecheck-frontend
	@echo "✅ Type checks passed"

# ── Tests ──────────────────────────────────────────────────
test-hub:
	@cd $(HUB_DIR) && \
		PYTHONPATH=.:..:../agent:../hub-backend $(PYTHON) -m pytest tests/ -v --tb=short \
		  --cov=hub_backend --cov-report=term-missing \
		  --cov-fail-under=80

test-agent:
	@cd $(AGENT_DIR) && \
		PYTHONPATH=.:..:../agent:../hub-backend $(PYTHON) -m pytest tests/ -v --tb=short \
		  --cov=agent --cov-report=term-missing

test-frontend:
	@cd $(FRONTEND_DIR) && npm test -- --run

test-unit: test-hub test-agent test-frontend
	@echo "✅ Unit tests passed"

test-integration:
	@cd $(HUB_DIR) && PYTHONPATH=.:..:../agent:../hub-backend $(PYTHON) -m pytest tests/test_integration_e2e.py tests/test_scoping.py tests/test_media_streaming.py -v

test-e2e:
	@cd tests && npx playwright test

test-security:
	@cd $(HUB_DIR) && PYTHONPATH=.:..:../agent:../hub-backend $(PYTHON) -m pytest tests/test_pentest_suite.py tests/test_stream_encryption.py tests/test_stream_authorization.py tests/test_transport_security.py tests/test_data_protection.py -v
	@echo "✅ Security tests passed"

test-all: test-unit test-integration test-security
	@echo "✅ All tests passed"

# ── Build ──────────────────────────────────────────────────
build:
	$(COMPOSE) -f $(COMPOSE_FILE) build

# ── Shells ─────────────────────────────────────────────────
shell-hub:
	$(COMPOSE) -f $(COMPOSE_FILE) exec hub-backend bash

shell-db:
	$(COMPOSE) -f $(COMPOSE_FILE) exec postgres psql -U nvrsms nvrsms

# ── Help ───────────────────────────────────────────────────
help:
	@echo ""
	@echo "NVRSMS Platform — Makefile targets:"
	@echo "  make up              Start all services via docker-compose"
	@echo "  make down            Stop and remove containers + volumes"
	@echo "  make logs            Follow service logs"
	@echo "  make jenkins-up      Build and start local Jenkins stack"
	@echo "  make jenkins-down    Tear down local Jenkins stack and volumes"
	@echo "  make jenkins-logs    Follow Jenkins container logs"
	@echo "  make jenkins-build   Build Jenkins agent container image"
	@echo "  make migrate         Run DB migrations (upgrade head)"
	@echo "  make lint            Lint hub + agent + frontend"
	@echo "  make typecheck       Type-check hub + agent + frontend"
	@echo "  make test-unit       Run unit test suite across all services"
	@echo "  make test-integration Run platform integration test suite"
	@echo "  make test-security   Run threat model & penetration tests"
	@echo "  make test-all        Run full automated test matrix"
	@echo "  make build           Build all platform Docker images"
	@echo ""
