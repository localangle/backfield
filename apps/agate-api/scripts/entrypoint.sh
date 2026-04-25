#!/bin/sh
set -e
export PYTHONPATH="/app/packages/backfield-db/src:${PYTHONPATH:-}"
python -c "from backfield_db.ensure_database import ensure_database_exists; ensure_database_exists()"
cd /app/packages/backfield-db
python -m alembic upgrade head
cd /app/apps/agate-api
if [ "${BACKFIELD_LOCAL_BOOTSTRAP:-0}" = "1" ]; then
  python -m api.local_bootstrap
fi
exec uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
