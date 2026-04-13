# Backfield — minimal developer surface (see `make help`)
COMPOSE_FILE := infra/docker-compose.yml
DC := docker compose -f $(COMPOSE_FILE)

.PHONY: help up up-detached down logs migrate reset-db test test-unit test-integration lint format bootstrap smoke

help:
	@echo "Backfield"
	@echo "  make up          - Start stack in foreground (logs attached; Ctrl+C stops)"
	@echo "  make up-detached - Same as up but background (-d)"
	@echo "  make down        - Stop stack"
	@echo "  make logs        - Follow compose logs"
	@echo "  make migrate     - Run Alembic (agate-api container)"
	@echo "  make reset-db    - Drop compose volumes (destructive)"
	@echo "  make test        - Unit + integration tests"
	@echo "  make test-unit   - Python unit tests (backfield-core)"
	@echo "  make test-integration - API smoke tests"
	@echo "  make lint        - Ruff check"
	@echo "  make format      - Ruff format"
	@echo "  make bootstrap   - uv sync (root) for local tooling"
	@echo "  make smoke       - Golden-path smoke against a live stack"

bootstrap:
	uv sync --all-packages

up:
	@echo "Starting Backfield stack (foreground)..."
	$(DC) up --build

up-detached:
	@echo "Starting Backfield stack (detached)..."
	$(DC) up -d --build

down:
	@echo "Stopping Backfield stack..."
	$(DC) down --remove-orphans

logs:
	$(DC) logs -f

migrate:
	$(DC) exec agate-api sh -c 'export PYTHONPATH=/app/packages/backfield-db/src && cd /app/packages/backfield-db && python -m alembic upgrade head'

reset-db:
	@echo "Removing Postgres volume (all local Backfield data)."
	$(DC) down -v

test: test-unit test-integration

test-unit:
	uv run pytest packages/backfield-core/tests -q

test-integration:
	uv run pytest tests -q

lint:
	uv run ruff check packages apps tests

format:
	uv run ruff format packages apps tests

smoke:
	uv run python scripts/smoke_agate_stack.py
