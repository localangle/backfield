# syntax=docker/dockerfile:1

FROM python:3.11-slim-trixie AS base

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Dependency pins come from package pyproject ranges for now; lock-based
# `uv sync --frozen` install is a follow-up.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc curl \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv==0.6.14

FROM base AS builder

COPY packages/backfield-db /app/packages/backfield-db
COPY packages/backfield-observability /app/packages/backfield-observability
COPY packages/backfield-ai /app/packages/backfield-ai
COPY packages/backfield-auth /app/packages/backfield-auth
COPY packages/backfield-agate /app/packages/backfield-agate
COPY packages/backfield-entities /app/packages/backfield-entities
COPY packages/backfield-events /app/packages/backfield-events
COPY apps/worker /app/apps/worker

RUN uv pip install --system /app/packages/backfield-db \
    && uv pip install --system /app/packages/backfield-observability \
    && uv pip install --system /app/packages/backfield-ai \
    && uv pip install --system /app/packages/backfield-auth \
    && uv pip install --system /app/packages/backfield-events \
    && uv pip install --system /app/packages/backfield-entities \
    && uv pip install --system /app/packages/backfield-agate \
    && uv pip install --system /app/apps/worker

FROM python:3.11-slim-trixie AS prod

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CELERY_WORKER_CONCURRENCY=16

ARG APP_VERSION=0.0.0-dev
ARG GIT_SHA=unknown
ARG BUILD_TIME=unknown
ENV APP_VERSION=${APP_VERSION} \
    GIT_SHA=${GIT_SHA} \
    BUILD_TIME=${BUILD_TIME}

# Pin OpenSSL to trixie-security (≥ 3.5.7-1~deb13u2) for CVE-2026-75803 before
# any further package removals. bookworm has no fixed openssl package yet.
# The final Python service does not invoke Perl; remove perl-base after that.
# No package management runs after this point.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        openssl \
        libssl3t64 \
        openssl-provider-legacy \
    && rm -rf /var/lib/apt/lists/* \
    && dpkg --purge --force-depends --force-remove-essential perl-base \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin appuser

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY apps/worker/scripts/entrypoint.sh /usr/local/bin/backfield-worker-entrypoint.sh
COPY LICENSE.md /app/LICENSE.md

RUN chmod +x /usr/local/bin/backfield-worker-entrypoint.sh \
    && chown -R appuser:appuser /app

USER appuser

ENTRYPOINT ["/usr/local/bin/backfield-worker-entrypoint.sh"]

FROM base AS dev

COPY packages/backfield-db /app/packages/backfield-db
COPY packages/backfield-observability /app/packages/backfield-observability
COPY packages/backfield-ai /app/packages/backfield-ai
COPY packages/backfield-auth /app/packages/backfield-auth
COPY packages/backfield-agate /app/packages/backfield-agate
COPY packages/backfield-entities /app/packages/backfield-entities
COPY packages/backfield-events /app/packages/backfield-events
COPY apps/worker /app/apps/worker

RUN pip install --no-cache-dir -e /app/packages/backfield-db \
    && pip install --no-cache-dir -e /app/packages/backfield-observability \
    && pip install --no-cache-dir -e /app/packages/backfield-ai \
    && pip install --no-cache-dir -e /app/packages/backfield-auth \
    && pip install --no-cache-dir -e /app/packages/backfield-events \
    && pip install --no-cache-dir -e /app/packages/backfield-entities \
    && pip install --no-cache-dir -e /app/packages/backfield-agate \
    && pip install --no-cache-dir "celery>=5.3.0" "redis>=5.0.0" "httpx>=0.27.0" \
    && pip install --no-cache-dir -e /app/apps/worker --no-deps

RUN chmod +x /app/apps/worker/scripts/entrypoint.sh

ENV PYTHONPATH=/app/apps/worker/src

WORKDIR /app/apps/worker
ENTRYPOINT ["/app/apps/worker/scripts/entrypoint.sh"]
