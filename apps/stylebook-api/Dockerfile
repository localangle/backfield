# syntax=docker/dockerfile:1

FROM python:3.11-slim-bookworm AS base

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Dependency pins come from package pyproject ranges for now; lock-based
# `uv sync --frozen` install is a follow-up.
RUN pip install --no-cache-dir uv==0.6.14

FROM base AS builder

COPY packages/backfield-db /app/packages/backfield-db
COPY packages/backfield-ai /app/packages/backfield-ai
COPY packages/backfield-auth /app/packages/backfield-auth
COPY packages/backfield-entities /app/packages/backfield-entities
COPY apps/stylebook-api /app/apps/stylebook-api

RUN uv pip install --system /app/packages/backfield-db \
    && uv pip install --system /app/packages/backfield-ai \
    && uv pip install --system /app/packages/backfield-entities \
    && uv pip install --system /app/packages/backfield-auth \
    && uv pip install --system /app/apps/stylebook-api

FROM python:3.11-slim-bookworm AS prod

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

ARG APP_VERSION=0.0.0-dev
ARG GIT_SHA=unknown
ARG BUILD_TIME=unknown
ENV APP_VERSION=${APP_VERSION} \
    GIT_SHA=${GIT_SHA} \
    BUILD_TIME=${BUILD_TIME}

# The final Python service does not invoke Perl. Remove the unpatched Debian
# runtime package; no package management runs after this point.
RUN dpkg --purge --force-depends --force-remove-essential perl-base \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin appuser

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY LICENSE.md /app/LICENSE.md

RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8003
CMD ["uvicorn", "stylebook_api.main:app", "--host", "0.0.0.0", "--port", "8003"]

FROM base AS dev

COPY packages/backfield-db /app/packages/backfield-db
COPY packages/backfield-ai /app/packages/backfield-ai
COPY packages/backfield-auth /app/packages/backfield-auth
COPY packages/backfield-entities /app/packages/backfield-entities
COPY apps/stylebook-api /app/apps/stylebook-api

RUN cd /app/packages/backfield-db && uv pip install --system -e . \
    && cd /app/packages/backfield-ai && uv pip install --system -e . \
    && cd /app/packages/backfield-entities && uv pip install --system -e . \
    && cd /app/packages/backfield-auth && uv pip install --system -e . \
    && cd /app/apps/stylebook-api && uv pip install --system -e .

ENV PYTHONPATH=/app/apps/stylebook-api/src

WORKDIR /app/apps/stylebook-api
EXPOSE 8003
CMD ["uvicorn", "stylebook_api.main:app", "--host", "0.0.0.0", "--port", "8003", "--reload"]
