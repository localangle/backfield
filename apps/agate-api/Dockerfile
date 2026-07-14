# syntax=docker/dockerfile:1

FROM python:3.11-slim-bookworm AS base

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc curl \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv

FROM base AS builder

COPY packages/backfield-db /app/packages/backfield-db
COPY packages/backfield-ai /app/packages/backfield-ai
COPY packages/backfield-agate /app/packages/backfield-agate
COPY packages/backfield-entities /app/packages/backfield-entities
COPY packages/backfield-auth /app/packages/backfield-auth
COPY packages/backfield-cli /app/packages/backfield-cli
COPY apps/agate-api /app/apps/agate-api

RUN uv pip install --system /app/packages/backfield-db \
    && uv pip install --system /app/packages/backfield-ai \
    && uv pip install --system /app/packages/backfield-entities \
    && uv pip install --system /app/packages/backfield-agate \
    && uv pip install --system /app/packages/backfield-auth \
    && uv pip install --system "rich>=13.0.0" \
    && uv pip install --system --no-deps --no-sources /app/packages/backfield-cli \
    && uv pip install --system /app/apps/agate-api

FROM python:3.11-slim-bookworm AS prod

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BACKFIELD_ALEMBIC_ROOT=/app/packages/backfield-db

ARG APP_VERSION=0.0.0-dev
ARG GIT_SHA=unknown
ARG BUILD_TIME=unknown
ENV APP_VERSION=${APP_VERSION} \
    GIT_SHA=${GIT_SHA} \
    BUILD_TIME=${BUILD_TIME}

# The final Python service does not invoke Perl. Remove the unpatched Debian
# runtime package (builders retain normal tooling); no package management runs
# after this point.
RUN dpkg --purge --force-depends --force-remove-essential perl-base

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
# Alembic assets are not packaged in the backfield-db wheel; copy them explicitly
# so backfield-migrate can resolve alembic.ini via BACKFIELD_ALEMBIC_ROOT.
COPY --from=builder /app/packages/backfield-db/alembic.ini /app/packages/backfield-db/alembic.ini
COPY --from=builder /app/packages/backfield-db/alembic /app/packages/backfield-db/alembic

EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM base AS dev

COPY packages/backfield-db /app/packages/backfield-db
COPY packages/backfield-ai /app/packages/backfield-ai
COPY packages/backfield-agate /app/packages/backfield-agate
COPY packages/backfield-entities /app/packages/backfield-entities
COPY packages/backfield-auth /app/packages/backfield-auth
COPY packages/backfield-cli /app/packages/backfield-cli
COPY apps/agate-api /app/apps/agate-api

RUN pip install --no-cache-dir -e /app/packages/backfield-db \
    && pip install --no-cache-dir -e /app/packages/backfield-ai \
    && pip install --no-cache-dir -e /app/packages/backfield-entities \
    && pip install --no-cache-dir -e /app/packages/backfield-agate \
    && pip install --no-cache-dir -e /app/packages/backfield-auth \
    && pip install --no-cache-dir -e /app/packages/backfield-cli \
    && pip install --no-cache-dir \
        "fastapi>=0.109.0" \
        "uvicorn[standard]>=0.27.0" \
        "celery>=5.3.0" \
        "redis>=5.0.0" \
        "pydantic>=2.0.0" \
    && pip install --no-cache-dir -e /app/apps/agate-api --no-deps

RUN chmod +x /app/apps/agate-api/scripts/entrypoint.sh

ENV PYTHONPATH=/app/apps/agate-api/src

WORKDIR /app/apps/agate-api
EXPOSE 8000
ENTRYPOINT ["/app/apps/agate-api/scripts/entrypoint.sh"]
