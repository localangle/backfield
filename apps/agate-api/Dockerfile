FROM python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends gcc curl && rm -rf /var/lib/apt/lists/*

COPY packages/agate-runtime /app/packages/agate-runtime
COPY packages/backfield-core /app/packages/backfield-core
COPY packages/backfield-db /app/packages/backfield-db
COPY packages/backfield-auth /app/packages/backfield-auth
COPY apps/agate-api /app/apps/agate-api

RUN pip install --no-cache-dir -e /app/packages/agate-runtime \
    && pip install --no-cache-dir -e /app/packages/backfield-core \
    && pip install --no-cache-dir -e /app/packages/backfield-db \
    && pip install --no-cache-dir -e /app/packages/backfield-auth \
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
