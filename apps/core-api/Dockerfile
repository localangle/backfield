# syntax=docker/dockerfile:1

FROM python:3.11-slim AS base

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN pip install --no-cache-dir uv

FROM base AS builder

COPY packages/backfield-db /app/packages/backfield-db
COPY packages/backfield-ai /app/packages/backfield-ai
COPY packages/backfield-entities /app/packages/backfield-entities
COPY packages/backfield-agate /app/packages/backfield-agate
COPY packages/backfield-auth /app/packages/backfield-auth
COPY apps/core-api /app/apps/core-api

RUN uv pip install --system /app/packages/backfield-db \
    && uv pip install --system /app/packages/backfield-ai \
    && uv pip install --system /app/packages/backfield-entities \
    && uv pip install --system /app/packages/backfield-agate \
    && uv pip install --system /app/packages/backfield-auth \
    && uv pip install --system /app/apps/core-api

FROM python:3.11-slim AS prod

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

ARG APP_VERSION=0.0.0-dev
ARG GIT_SHA=unknown
ARG BUILD_TIME=unknown
ENV APP_VERSION=${APP_VERSION} \
    GIT_SHA=${GIT_SHA} \
    BUILD_TIME=${BUILD_TIME}

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

EXPOSE 8004
CMD ["uvicorn", "core_api.main:app", "--host", "0.0.0.0", "--port", "8004"]

FROM base AS dev

COPY packages/backfield-db /app/packages/backfield-db
COPY packages/backfield-ai /app/packages/backfield-ai
COPY packages/backfield-entities /app/packages/backfield-entities
COPY packages/backfield-agate /app/packages/backfield-agate
COPY packages/backfield-auth /app/packages/backfield-auth
COPY apps/core-api /app/apps/core-api

RUN cd /app/packages/backfield-db && uv pip install --system -e . \
    && cd /app/packages/backfield-ai && uv pip install --system -e . \
    && cd /app/packages/backfield-entities && uv pip install --system -e . \
    && cd /app/packages/backfield-agate && uv pip install --system -e . \
    && cd /app/packages/backfield-auth && uv pip install --system -e . \
    && cd /app/apps/core-api && uv pip install --system -e .

ENV PYTHONPATH=/app/apps/core-api/src

WORKDIR /app/apps/core-api
EXPOSE 8004
CMD ["uvicorn", "core_api.main:app", "--host", "0.0.0.0", "--port", "8004"]
