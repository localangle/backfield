FROM python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

RUN pip install --no-cache-dir uv

COPY packages/backfield-db /app/packages/backfield-db
COPY packages/backfield-ai /app/packages/backfield-ai
COPY packages/backfield-stylebook /app/packages/backfield-stylebook
COPY packages/backfield-auth /app/packages/backfield-auth
COPY apps/core-api /app/apps/core-api

# Local packages are not on PyPI: db → ai → stylebook → auth → app.
RUN cd /app/packages/backfield-db && uv pip install --system -e . \
    && cd /app/packages/backfield-ai && uv pip install --system -e . \
    && cd /app/packages/backfield-stylebook && uv pip install --system -e . \
    && cd /app/packages/backfield-auth && uv pip install --system -e . \
    && cd /app/apps/core-api && uv pip install --system -e .

ENV PYTHONPATH=/app/apps/core-api/src

WORKDIR /app/apps/core-api
EXPOSE 8004
CMD ["uvicorn", "core_api.main:app", "--host", "0.0.0.0", "--port", "8004"]
