.PHONY: up down restart logs migrate migrate-down migrate-history \
        test-hub test-agent test-e2e test-all lint lint-hub lint-agent lint-frontend \
        shell-hub shell-db build help

# ── Configuration ──────────────────────────────────────────
COMPOSE        := docker compose
COMPOSE_FILE   := infra/docker-compose.yml
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

# ── Database Migrations ────────────────────────────────────
migrate:
	@cd $(HUB_DIR) && alembic upgrade head

migrate-down:
	@cd $(HUB_DIR) && alembic downgrade base

migrate-history:
	@cd $(HUB_DIR) && alembic history --verbose

# ── Tests ──────────────────────────────────────────────────
test-hub:
	@cd $(HUB_DIR) && \
		$(PYTHON) -m pytest tests/ -v --tb=short \
		  --cov=hub_backend --cov-report=term-missing \
		  --cov-fail-under=80

test-agent:
	@cd $(AGENT_DIR) && \
		$(PYTHON) -m pytest tests/ -v --tb=short \
		  --cov=agent --cov-report=term-missing

test-e2e:
	@cd tests && npx playwright test

test-all: test-hub test-agent
	@echo "✅ All tests passed"

# ── Lint / Format ──────────────────────────────────────────
lint-hub:
	@cd $(HUB_DIR) && ruff check . && ruff format --check .

lint-agent:
	@cd $(AGENT_DIR) && ruff check . && ruff format --check .

lint-frontend:
	@cd $(FRONTEND_DIR) && npm run lint

lint: lint-hub lint-agent
	@echo "✅ Lint passed"

# ── Shells ─────────────────────────────────────────────────
shell-hub:
	$(COMPOSE) -f $(COMPOSE_FILE) exec hub-backend bash

shell-db:
	$(COMPOSE) -f $(COMPOSE_FILE) exec postgres psql -U nvrsms nvrsms

# ── Help ───────────────────────────────────────────────────
help:
	@echo ""
	@echo "NVRSMS Platform — Makefile targets:"
	@echo "  make up              Start all services"
	@echo "  make down            Stop and remove containers + volumes"
	@echo "  make logs            Follow service logs"
	@echo "  make migrate         Run DB migrations (upgrade head)"
	@echo "  make migrate-down    Roll back all migrations"
	@echo "  make test-hub        Run hub-backend tests"
	@echo "  make test-agent      Run agent tests"
	@echo "  make test-all        Run all tests"
	@echo "  make lint            Lint hub + agent"
	@echo "  make shell-hub       Bash shell in hub-backend container"
	@echo "  make shell-db        psql shell in postgres container"
	@echo ""
