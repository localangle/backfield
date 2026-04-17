FROM python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

RUN pip install --no-cache-dir uv

COPY packages/backfield-db /app/packages/backfield-db
COPY packages/backfield-auth /app/packages/backfield-auth
COPY apps/stylebook-api /app/apps/stylebook-api

# Local packages are not on PyPI; install deps before the app (auth depends on db).
RUN cd /app/packages/backfield-db && uv pip install --system -e . \
    && cd /app/packages/backfield-auth && uv pip install --system -e . \
    && cd /app/apps/stylebook-api && uv pip install --system -e .

ENV PYTHONPATH=/app/apps/stylebook-api/src

WORKDIR /app/apps/stylebook-api
EXPOSE 8003
CMD ["uvicorn", "stylebook_api.main:app", "--host", "0.0.0.0", "--port", "8003", "--reload"]
