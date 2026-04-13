FROM python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends gcc curl && rm -rf /var/lib/apt/lists/*

COPY packages/backfield-agate-runtime /app/packages/backfield-agate-runtime
COPY packages/backfield-core /app/packages/backfield-core
COPY packages/backfield-db /app/packages/backfield-db
COPY apps/worker /app/apps/worker

RUN pip install --no-cache-dir -e /app/packages/backfield-agate-runtime \
    && pip install --no-cache-dir -e /app/packages/backfield-core \
    && pip install --no-cache-dir -e /app/packages/backfield-db \
    && pip install --no-cache-dir "celery>=5.3.0" "redis>=5.0.0" \
    && pip install --no-cache-dir -e /app/apps/worker --no-deps

ENV PYTHONPATH=/app/apps/worker/src

WORKDIR /app/apps/worker
CMD ["celery", "-A", "worker.tasks", "worker", "--loglevel=info", "-Q", "agate", "--concurrency=2"]
