# Backfield — common developer commands (see `make help`)
COMPOSE_FILE := infra/docker-compose.yml
DC := docker compose -f $(COMPOSE_FILE) --env-file .env
BACKFIELD := ./scripts/backfield
APP_VERSION ?= 0.0.0-dev
GIT_SHA ?= unknown
BUILD_TIME ?= unknown
DOCKER_BAKE_ENV := APP_VERSION=$(APP_VERSION) GIT_SHA=$(GIT_SHA) BUILD_TIME=$(BUILD_TIME)

.PHONY: help \
	bootstrap install-cli-shim install-user-cli uninstall-user-cli \
	up up-detached down logs migrate migrate-host reset-db clear-entity-data \
	docker-trim docker-trim-full \
	lint format test smoke smoke-fast \
	ui-bootstrap ui-typecheck ui-test ui-build agate-ui-build stylebook-ui-build \
	api-playground-bootstrap api-playground-lint api-playground-test api-playground-build \
	docker-build-prod-apis docker-build-prod-worker

help:
	@echo "Backfield"
	@echo ""
	@echo "Local stack"
	@echo "  make bootstrap           - uv sync + install project launcher into .venv/bin"
	@echo "  make up / up-detached    - Start stack in the background (wraps backfield up)"
	@echo "  make down                - Stop stack (project only; no global Docker prune)"
	@echo "  make logs                - Follow stack logs"
	@echo "  make migrate             - Run Alembic via compose migrate service"
	@echo "  make migrate-host        - Run Alembic on the host (Postgres on :5433)"
	@echo "  make reset-db            - Wipe compose volumes and database"
	@echo "  make clear-entity-data   - Truncate entity + run data (BACKFIELD_CONFIRM_CLEAR=1)"
	@echo "  make docker-trim         - Opt-in: reclaim unused Docker data host-wide (keeps volumes)"
	@echo "  make docker-trim-full    - Opt-in: docker-trim plus unused volume prune"
	@echo "  make install-user-cli    - Symlink ~/.local/bin/backfield"
	@echo ""
	@echo "Validation"
	@echo "  make lint / format / test"
	@echo "  make ui-typecheck / ui-test"
	@echo "  make api-playground-lint / api-playground-test"
	@echo "  make smoke               - Golden Agate-to-Stylebook handoff"
	@echo "  make smoke-fast          - Auth + basic Agate + basic Stylebook"
	@echo "  Specialized smoke scripts: uv run python -u tests/smoke/<script>.py"
	@echo ""
	@echo "Deploy builds"
	@echo "  make ui-build            - Production-build all UIs (includes typecheck)"
	@echo "  make docker-build-prod-apis / docker-build-prod-worker"

# --- Local stack -------------------------------------------------------------

bootstrap:
	uv sync --all-packages --reinstall-package backfield-cli --reinstall-package backfield-db
	@$(MAKE) --no-print-directory install-cli-shim
	@echo ""
	@echo "Project launcher ready. In this shell, run:"
	@echo "  source .venv/bin/activate"
	@echo "Then: backfield init | up | down | doctor | ..."
	@echo "Optional (no venv activate): make install-user-cli"

install-cli-shim:
	@test -d .venv/bin || (echo "error: .venv missing; run 'uv sync' or 'make bootstrap' first." >&2 && exit 1)
	@chmod +x scripts/backfield scripts/install-cli-shim.sh
	@./scripts/install-cli-shim.sh

install-user-cli:
	@chmod +x scripts/backfield scripts/install-user-cli.sh
	@./scripts/install-user-cli.sh

uninstall-user-cli:
	@chmod +x scripts/uninstall-user-cli.sh
	@./scripts/uninstall-user-cli.sh

up:
	$(BACKFIELD) up

up-detached:
	$(BACKFIELD) up --detached

down:
	$(BACKFIELD) down

logs:
	$(BACKFIELD) logs

migrate:
	$(DC) run --rm migrate

migrate-host:
	$(BACKFIELD) migrate

reset-db:
	$(BACKFIELD) reset-db --yes

clear-entity-data:
	@if [ "$(BACKFIELD_CONFIRM_CLEAR)" != "1" ]; then \
		echo "Destructive: truncates substrate_*, stylebook_* entity, and Agate run tables."; \
		echo "Preserves stylebook catalog rows (stylebook, stylebook_membership, stylebook_slug_redirect)."; \
		echo "Preserves Agate graphs/templates and backfield_* identity tables."; \
		echo "Re-run: BACKFIELD_CONFIRM_CLEAR=1 make clear-entity-data"; \
		exit 1; \
	fi
	$(BACKFIELD) clear-entity-data --yes

# After `compose down`, Postgres volumes are unreferenced; volume prune can delete them.
# Default trim keeps volumes so `make down` then `make up` preserves local data.
docker-trim:
	@echo "Pruning unused Docker data (stopped containers, dangling images, unused networks, build cache)..."
	docker system prune -f
	@echo "docker-trim done."

docker-trim-full: docker-trim
	@echo "Pruning unused Docker volumes..."
	docker volume prune -f
	@echo "docker-trim-full done."

# --- Validation --------------------------------------------------------------

lint:
	uv run ruff check packages apps tests

format:
	uv run ruff format packages apps tests

test:
	uv run pytest packages/backfield-agate/tests packages/backfield-auth/tests packages/backfield-db/tests packages/backfield-cli/tests -q
	uv run pytest tests -q

smoke:
	uv run python -u tests/smoke/golden_path_stack.py

smoke-fast:
	uv run python -u tests/smoke/smoke_auth.py
	uv run python -u tests/smoke/smoke_agate_basic.py
	uv run python -u tests/smoke/smoke_stylebook_basic.py

# --- Frontend validation / deploy builds ------------------------------------

api-playground-bootstrap:
	cd packages/backfield-ui && npm ci
	cd apps/api-playground && npm ci

ui-bootstrap:
	cd packages/backfield-ui && npm ci
	cd apps/agate-ui && npm ci
	cd apps/stylebook-ui && npm ci
	cd apps/api-playground && npm ci

ui-typecheck:
	cd packages/backfield-ui && npm ci
	cd apps/agate-ui && npm ci && npm run sync-nodes && npx tsc --noEmit
	cd apps/stylebook-ui && npm ci && npx tsc --noEmit
	cd apps/api-playground && npm ci && npm run lint

ui-test:
	cd packages/backfield-ui && npm ci && npm test
	cd apps/agate-ui && npm ci && npm run sync-nodes && npm test
	cd apps/stylebook-ui && npm ci && npm test
	cd apps/api-playground && npm ci && npm test

agate-ui-build:
	cd packages/backfield-ui && npm ci
	cd apps/agate-ui && npm ci && npm run sync-nodes && npm run build:check

stylebook-ui-build:
	cd packages/backfield-ui && npm ci
	cd apps/stylebook-ui && npm ci && npm run build

api-playground-lint:
	cd packages/backfield-ui && npm ci
	cd apps/api-playground && npm ci && npm run lint

api-playground-test:
	cd packages/backfield-ui && npm ci
	cd apps/api-playground && npm ci && npm test

api-playground-build:
	cd packages/backfield-ui && npm ci
	cd apps/api-playground && npm ci && npm run build

ui-build: agate-ui-build stylebook-ui-build api-playground-build

docker-build-prod-apis:
	$(DOCKER_BAKE_ENV) docker buildx bake agate-api core-api stylebook-api --load

docker-build-prod-worker:
	$(DOCKER_BAKE_ENV) docker buildx bake worker --load
