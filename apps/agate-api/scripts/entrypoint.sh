#!/bin/sh
set -e
export PYTHONPATH="/app/apps/agate-api/src:${PYTHONPATH:-}"
cd /app/apps/agate-api
if [ "${BACKFIELD_LOCAL_BOOTSTRAP:-0}" = "1" ]; then
  python -m api.local_bootstrap
fi
exec uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
