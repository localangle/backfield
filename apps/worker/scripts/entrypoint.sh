#!/bin/sh
set -e

if [ -d /app/apps/worker/src ]; then
  export PYTHONPATH="/app/apps/worker/src${PYTHONPATH:+:$PYTHONPATH}"
fi

CONCURRENCY="${CELERY_WORKER_CONCURRENCY:-16}"
PREFETCH_MULTIPLIER="${CELERY_PREFETCH_MULTIPLIER:-1}"
MAX_TASKS_PER_CHILD="${CELERY_MAX_TASKS_PER_CHILD:-1}"
MAX_MEMORY_PER_CHILD_KB="${CELERY_MAX_MEMORY_PER_CHILD_KB:-1048576}"
LOGLEVEL="${CELERY_LOG_LEVEL:-info}"
QUEUE="${CELERY_QUEUE:-agate}"

python -c "from worker.startup import log_worker_startup; log_worker_startup()"

exec celery -A worker.tasks worker \
  --loglevel="${LOGLEVEL}" \
  -Q "${QUEUE}" \
  --concurrency "${CONCURRENCY}" \
  --prefetch-multiplier "${PREFETCH_MULTIPLIER}" \
  --max-tasks-per-child "${MAX_TASKS_PER_CHILD}" \
  --max-memory-per-child "${MAX_MEMORY_PER_CHILD_KB}"
