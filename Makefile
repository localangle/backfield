# Backfield — minimal developer surface (see `make help`)
COMPOSE_FILE := infra/docker-compose.yml
DC := docker compose -f $(COMPOSE_FILE) --env-file .env
APP_VERSION ?= 0.0.0-dev
GIT_SHA ?= unknown
BUILD_TIME ?= unknown
DOCKER_PROD_BUILD_ARGS := --build-arg APP_VERSION=$(APP_VERSION) --build-arg GIT_SHA=$(GIT_SHA) --build-arg BUILD_TIME=$(BUILD_TIME)

.PHONY: help up up-detached down logs migrate reset-db clear-entity-data docker-prune-build docker-prune-system docker-prune-volumes docker-trim docker-trim-full docker-build-prod-apis docker-build-prod-agate-api docker-build-prod-core-api docker-build-prod-stylebook-api docker-build-prod-worker test test-unit test-integration lint format bootstrap smoke smoke-auth smoke-agate-basic smoke-stylebook-basic smoke-agate-stylebook-handoff smoke-worker-async smoke-stylebook-editorial smoke-s3-batch smoke-stylebook-import-export smoke-fast smoke-runtime smoke-slower smoke-place-geocode smoke-place-geocode-stack smoke-people smoke-people-stack smoke-organizations smoke-organizations-stack smoke-article-metadata smoke-article-metadata-stack smoke-custom-extract smoke-custom-extract-stack smoke-parallel-graph smoke-parallel-graph-stack stylebook-ui-build

help:
	@echo "Backfield"
	@echo "  make up          - Start stack in foreground (logs attached; Ctrl+C stops)"
	@echo "  make up-detached - Same as up but background (-d)"
	@echo "  make down        - Stop stack (docker compose down), then docker-trim"
	@echo "  make logs        - Follow compose logs"
	@echo "  make migrate     - Run Alembic via one-off compose migrate service"
	@echo "  make migrate-host - Run Alembic on host (uv run backfield migrate; Postgres on :5433)"
	@echo "  make reset-db    - Stop stack and remove compose volumes (Postgres data, etc.)"
	@echo "  make clear-entity-data - Truncate substrate/stylebook entity + Agate runs (BACKFIELD_CONFIRM_CLEAR=1)"
	@echo "  make docker-prune-build   - Free build cache only (docker builder prune -f)"
	@echo "  make docker-prune-system  - Remove stopped containers, dangling images, unused networks (docker system prune -f)"
	@echo "  make docker-prune-volumes - Remove unused volumes (docker volume prune -f); can delete DB data after down"
	@echo "  make docker-trim          - docker system prune -f only (safe for Postgres/compose volumes across down/up)"
	@echo "  make docker-trim-full     - docker-trim then docker-prune-volumes (aggressive disk reclaim)"
	@echo "  make test        - Unit + integration tests"
	@echo "  make test-unit   - Python unit tests (agate-runtime)"
	@echo "  make test-integration - API smoke tests"
	@echo "  make lint        - Ruff check"
	@echo "  make format      - Ruff format"
	@echo "  make bootstrap   - uv sync (root) for local tooling"
	@echo "  make smoke       - Agate-to-Stylebook handoff smoke against a live stack"
	@echo "  make smoke-fast  - Auth + basic Agate + basic Stylebook smoke bundle"
	@echo "  make smoke-runtime - Handoff + worker lifecycle smoke bundle"
	@echo "  make smoke-slower - Editorial + import + S3 batch smoke bundle"
	@echo "  make smoke-place-geocode - In-process PlaceExtract + GeocodeAgent corpus (not CI)"
	@echo "  make smoke-place-geocode-stack - Same script --via-agate-api (enqueue one graph run)"
	@echo "  make smoke-people - In-process PersonExtract + DBOutput demo (not CI)"
	@echo "  make smoke-people-stack - Same script --via-agate-api (People starter graph)"
	@echo "  make smoke-organizations - In-process OrganizationExtract + DBOutput demo (not CI)"
	@echo "  make smoke-organizations-stack - Same script --via-agate-api (Organizations starter)"
	@echo "  make smoke-article-metadata - In-process ArticleMetadata + DBOutput demo (not CI)"
	@echo "  make smoke-article-metadata-stack - Same script --via-agate-api (Article Metadata starter)"
	@echo "  make smoke-custom-extract - In-process CustomExtract + DBOutput demo (not CI)"
	@echo "  make smoke-custom-extract-stack - Same script --via-agate-api (Custom Extract starter)"
	@echo "  make smoke-parallel-graph - Fan-out level parallelism timing (in-process, not CI)"
	@echo "  make smoke-parallel-graph-stack - Same script --via-agate-api (level + multi-item timing)"
	@echo "  make stylebook-ui-build - Typecheck and production-build apps/stylebook-ui"
	@echo "  make docker-build-prod-apis - Build production targets for agate/core/stylebook APIs"
	@echo "  make docker-build-prod-worker - Build production target for the Celery worker"

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
	$(DC) down
	@$(MAKE) --no-print-directory docker-trim

logs:
	$(DC) logs -f

migrate:
	$(DC) run --rm migrate

migrate-host:
	uv run backfield migrate

reset-db:
	@echo "Removing Postgres volume (all local Backfield data)."
	$(DC) down -v

clear-entity-data:
	@if [ "$(BACKFIELD_CONFIRM_CLEAR)" != "1" ]; then \
		echo "Destructive: truncates substrate_*, stylebook_* entity, and Agate run tables."; \
		echo "Preserves stylebook catalog rows (stylebook, stylebook_membership, stylebook_slug_redirect)."; \
		echo "Preserves Agate graphs/templates and backfield_* identity tables."; \
		echo "Re-run: BACKFIELD_CONFIRM_CLEAR=1 make clear-entity-data"; \
		exit 1; \
	fi
	BACKFIELD_CONFIRM_CLEAR=1 uv run python packages/backfield-db/scripts/clear_entity_data.py

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
# Default trim: system prune only so `make down` then `make up` keeps DB data.
docker-trim: docker-prune-system
	@echo "docker-trim done."

docker-trim-full: docker-trim docker-prune-volumes
	@echo "docker-trim-full done."

docker-build-prod-agate-api:
	docker build -f apps/agate-api/Dockerfile --target prod $(DOCKER_PROD_BUILD_ARGS) -t backfield-agate-api:prod .

docker-build-prod-core-api:
	docker build -f apps/core-api/Dockerfile --target prod $(DOCKER_PROD_BUILD_ARGS) -t backfield-core-api:prod .

docker-build-prod-stylebook-api:
	docker build -f apps/stylebook-api/Dockerfile --target prod $(DOCKER_PROD_BUILD_ARGS) -t backfield-stylebook-api:prod .

docker-build-prod-apis: docker-build-prod-agate-api docker-build-prod-core-api docker-build-prod-stylebook-api

docker-build-prod-worker:
	docker build -f apps/worker/Dockerfile --target prod $(DOCKER_PROD_BUILD_ARGS) -t backfield-worker:prod .

test: test-unit test-integration

test-unit:
	uv run pytest packages/backfield-agate/tests packages/backfield-auth/tests packages/backfield-db/tests packages/backfield-cli/tests -q

test-integration:
	uv run pytest tests -q

lint:
	uv run ruff check packages apps tests

format:
	uv run ruff format packages apps tests

smoke: smoke-agate-stylebook-handoff

smoke-auth:
	uv run python -u tests/smoke/smoke_auth.py

smoke-agate-basic:
	uv run python -u tests/smoke/smoke_agate_basic.py

smoke-stylebook-basic:
	uv run python -u tests/smoke/smoke_stylebook_basic.py

smoke-agate-stylebook-handoff:
	uv run python -u tests/smoke/golden_path_stack.py

smoke-worker-async:
	uv run python -u tests/smoke/smoke_worker_async.py

smoke-stylebook-editorial:
	uv run python -u tests/smoke/smoke_stylebook_editorial.py

smoke-s3-batch:
	uv run python -u tests/smoke/smoke_s3_batch.py

smoke-stylebook-import-export:
	uv run python -u tests/smoke/smoke_stylebook_import_export.py

smoke-fast: smoke-auth smoke-agate-basic smoke-stylebook-basic

smoke-runtime: smoke-agate-stylebook-handoff smoke-worker-async

smoke-slower: smoke-stylebook-editorial smoke-stylebook-import-export smoke-s3-batch

smoke-place-geocode:
	uv run python -u tests/smoke/place_geocode_smoke.py

smoke-place-geocode-stack:
	uv run python -u tests/smoke/place_geocode_smoke.py --via-agate-api

smoke-people:
	uv run python -u tests/smoke/smoke_people_stack.py

smoke-people-stack:
	uv run python -u tests/smoke/smoke_people_stack.py --via-agate-api

smoke-organizations:
	uv run python -u tests/smoke/smoke_organizations_stack.py

smoke-organizations-stack:
	uv run python -u tests/smoke/smoke_organizations_stack.py --via-agate-api

smoke-article-metadata:
	uv run python -u tests/smoke/smoke_article_metadata_stack.py

smoke-article-metadata-stack:
	uv run python -u tests/smoke/smoke_article_metadata_stack.py --via-agate-api

smoke-custom-extract:
	uv run python -u tests/smoke/smoke_custom_extract_stack.py

smoke-custom-extract-stack:
	uv run python -u tests/smoke/smoke_custom_extract_stack.py --via-agate-api

smoke-parallel-graph:
	uv run python -u tests/smoke/smoke_parallel_graph.py

smoke-parallel-graph-stack:
	uv run python -u tests/smoke/smoke_parallel_graph.py --via-agate-api

stylebook-ui-build:
	cd packages/backfield-ui && npm ci
	cd apps/stylebook-ui && npm ci && npm run build
