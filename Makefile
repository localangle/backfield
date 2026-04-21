# Backfield — minimal developer surface (see `make help`)
COMPOSE_FILE := infra/docker-compose.yml
DC := docker compose -f $(COMPOSE_FILE)

.PHONY: help up up-detached down logs migrate reset-db docker-prune-build docker-prune-system docker-prune-volumes docker-trim docker-trim-full test test-unit test-integration lint format bootstrap smoke stylebook-ui-build

help:
	@echo "Backfield"
	@echo "  make up          - Start stack in foreground (logs attached; Ctrl+C stops)"
	@echo "  make up-detached - Same as up but background (-d)"
	@echo "  make down        - Stop stack, then docker-trim (system prune only; keeps compose DB volumes)"
	@echo "  make logs        - Follow compose logs"
	@echo "  make migrate     - Run Alembic (agate-api container)"
	@echo "  make reset-db    - Stop stack and remove compose volumes (Postgres data, etc.)"
	@echo "  make docker-prune-build   - Free build cache only (docker builder prune -f)"
	@echo "  make docker-prune-system  - Remove stopped containers, dangling images, unused networks (docker system prune -f)"
	@echo "  make docker-prune-volumes - Remove unused volumes (docker volume prune -f); can delete DB data after down"
	@echo "  make docker-trim          - docker system prune -f only (safe for Postgres/compose volumes across down/up)"
	@echo "  make docker-trim-full     - docker-trim then docker-prune-volumes (aggressive disk reclaim)"
	@echo "  make test        - Unit + integration tests"
	@echo "  make test-unit   - Python unit tests (backfield-core)"
	@echo "  make test-integration - API smoke tests"
	@echo "  make lint        - Ruff check"
	@echo "  make format      - Ruff format"
	@echo "  make bootstrap   - uv sync (root) for local tooling"
	@echo "  make smoke       - Golden-path smoke against a live stack"
	@echo "  make stylebook-ui-build - Typecheck and production-build apps/stylebook-ui"

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
	@$(MAKE) --no-print-directory docker-trim

logs:
	$(DC) logs -f

migrate:
	$(DC) exec agate-api sh -c 'export PYTHONPATH=/app/packages/backfield-db/src && cd /app/packages/backfield-db && python -m alembic upgrade head'

reset-db:
	@echo "Removing Postgres volume (all local Backfield data)."
	$(DC) down -v

docker-prune-build:
	@echo "Pruning Docker build cache..."
	docker builder prune -f

docker-prune-system:
	@echo "Pruning unused Docker data (stopped containers, dangling images, unused networks, build cache)..."
	docker system prune -f

docker-prune-volumes:
	@echo "Pruning unused Docker volumes (anything not referenced by a container, including compose DB volumes after down)..."
	docker volume prune -f

# After `compose down`, Postgres (and other compose) volumes are unreferenced; `volume prune` can delete them.
# Default trim matches agate-ai-platform local dev: system prune only so `make down` then `make up` keeps DB data.
docker-trim: docker-prune-system
	@echo "docker-trim done."

docker-trim-full: docker-trim docker-prune-volumes
	@echo "docker-trim-full done."

test: test-unit test-integration

test-unit:
	uv run pytest packages/backfield-core/tests packages/backfield-auth/tests -q

test-integration:
	uv run pytest tests -q

lint:
	uv run ruff check packages apps tests

format:
	uv run ruff format packages apps tests

smoke:
	uv run python -u tests/smoke/golden_path_stack.py

stylebook-ui-build:
	cd apps/stylebook-ui && npm ci && npm run build
