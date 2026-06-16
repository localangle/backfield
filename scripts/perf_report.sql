-- Agate run performance report (local Postgres).
-- Usage:
--   psql "$BACKFIELD_DATABASE_URL" -v run_id='<agate_run uuid>' -f scripts/perf_report.sql
--
-- Replace :run_id with a concrete run id before running, or pass -v run_id=...

\echo '=== Run summary ==='
SELECT
    r.id AS run_id,
    r.status,
    r.graph_id,
    COUNT(i.id) AS item_count,
    COUNT(*) FILTER (WHERE i.status = 'succeeded') AS succeeded,
    COUNT(*) FILTER (WHERE i.status = 'failed') AS failed,
    MIN(i.updated_at) AS first_item_done,
    MAX(i.updated_at) AS last_item_done,
    EXTRACT(EPOCH FROM (MAX(i.updated_at) - MIN(i.updated_at))) AS item_window_seconds
FROM agate_run r
JOIN agate_processed_item i ON i.run_id = r.id
WHERE r.id = :'run_id'
GROUP BY r.id, r.status, r.graph_id;

\echo '=== LLM calls by node type ==='
SELECT
    COALESCE(c.node_type, '(unknown)') AS node_type,
    COUNT(*) AS call_count,
    COUNT(*) FILTER (WHERE c.status = 'failed') AS failed_count,
    ROUND(AVG(c.latency_ms) / 1000.0, 2) AS avg_latency_s,
    ROUND(SUM(c.latency_ms) / 1000.0, 2) AS total_latency_s
FROM backfield_ai_call_record c
WHERE c.run_id = :'run_id'
GROUP BY 1
ORDER BY total_latency_s DESC NULLS LAST;

\echo '=== DBOutput adjudication failures ==='
SELECT
    c.error_type,
    COUNT(*) AS failures,
    ROUND(AVG(c.latency_ms) / 1000.0, 2) AS avg_latency_s
FROM backfield_ai_call_record c
WHERE c.run_id = :'run_id'
  AND c.node_type = 'DBOutput'
  AND c.status = 'failed'
GROUP BY 1
ORDER BY failures DESC;

\echo '=== GeocodeAgent call volume per item ==='
SELECT
    c.processed_item_id,
    COUNT(*) AS geocode_llm_calls,
    ROUND(SUM(c.latency_ms) / 1000.0, 2) AS geocode_llm_seconds
FROM backfield_ai_call_record c
WHERE c.run_id = :'run_id'
  AND c.node_type = 'GeocodeAgent'
GROUP BY 1
ORDER BY geocode_llm_seconds DESC;

\echo '=== Effective parallelism (LLM call overlap window) ==='
WITH bounds AS (
    SELECT
        MIN(c.created_at) AS window_start,
        MAX(c.created_at) AS window_end,
        SUM(c.latency_ms) / 1000.0 AS total_model_seconds
    FROM backfield_ai_call_record c
    WHERE c.run_id = :'run_id'
      AND c.status = 'succeeded'
)
SELECT
    window_start,
    window_end,
    ROUND(total_model_seconds, 2) AS total_model_seconds,
    ROUND(EXTRACT(EPOCH FROM (window_end - window_start)), 2) AS window_seconds,
    CASE
        WHEN EXTRACT(EPOCH FROM (window_end - window_start)) > 0
        THEN ROUND(total_model_seconds / EXTRACT(EPOCH FROM (window_end - window_start)), 2)
        ELSE NULL
    END AS effective_parallelism
FROM bounds;

\echo '=== Concurrency env checklist (manual) ==='
\echo 'Confirm in worker logs / compose: CELERY_WORKER_CONCURRENCY=16, BACKFIELD_PARALLEL_GRAPH_LEVELS=1,'
\echo 'CANONICAL_ADJUDICATION_MAX_CONCURRENT=8, BACKFIELD_SQLALCHEMY_POOL_SIZE=2, MAX_OVERFLOW=3.'
