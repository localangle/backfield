FROM python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends gcc curl && rm -rf /var/lib/apt/lists/*

COPY packages/backfield-db /app/packages/backfield-db
COPY packages/backfield-ai /app/packages/backfield-ai
COPY packages/backfield-agate /app/packages/backfield-agate
COPY packages/backfield-entities /app/packages/backfield-entities
COPY apps/worker /app/apps/worker

# Local packages are not on PyPI: db → ai → entities → agate → app.
RUN pip install --no-cache-dir -e /app/packages/backfield-db \
    && pip install --no-cache-dir -e /app/packages/backfield-ai \
    && pip install --no-cache-dir -e /app/packages/backfield-entities \
    && pip install --no-cache-dir -e /app/packages/backfield-agate \
    && pip install --no-cache-dir "celery>=5.3.0" "redis>=5.0.0" \
    && pip install --no-cache-dir -e /app/apps/worker --no-deps

ENV PYTHONPATH=/app/apps/worker/src

WORKDIR /app/apps/worker
CMD ["celery", "-A", "worker.tasks", "worker", "--loglevel=info", "-Q", "agate", "--concurrency=8"]
