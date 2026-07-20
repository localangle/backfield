/**
 * Agate API client — Backfield agate-api.
 */

import {
  normalizeProcessedItemArticleEmbedding,
  type ProcessedItemArticleEmbedding,
} from '@/lib/review/content/articleEmbeddingDisplay'
import {
  normalizeProcessedItemArticleMetaRows,
  type ProcessedItemArticleMetaRow,
} from '@/lib/review/content/articleMetaDisplay'
import {
  normalizeProcessedItemConnections,
  type ProcessedItemConnections,
} from '@/lib/review/content/connectionsDisplay'
import {
  normalizeProcessedItemSemanticIndexing,
  type ProcessedItemSemanticIndexing,
} from '@/lib/review/content/semanticIndexingDisplay'

export type {
  ProcessedItemArticleEmbedding,
  ProcessedItemArticleEmbeddingStatus,
} from '@/lib/review/content/articleEmbeddingDisplay'
export type {
  ProcessedItemArticleMetaRow,
} from '@/lib/review/content/articleMetaDisplay'
export type {
  ProcessedItemConnections,
  ProcessedItemConnectionsStatus,
} from '@/lib/review/content/connectionsDisplay'
export type {
  ProcessedItemSemanticIndexing,
  ProcessedItemSemanticIndexingStatus,
} from '@/lib/review/content/semanticIndexingDisplay'

/** Agate API base. Default `/api/agate` uses Vite dev proxy to the Agate service (same-origin cookies). */
export const API_BASE =
  import.meta.env.VITE_API_BASE ||
  import.meta.env.VITE_AGATE_API_BASE ||
  import.meta.env.VITE_REWRITE_API_BASE ||
  '/api/agate'

export interface Project {
  id: number
  name: string
  slug: string
  organization_id: number
  system_prompt?: string
  created_at: string
  updated_at?: string
  workspace_id?: number | null
  workspace_stylebook_id?: number | null
  workspace_stylebook_name?: string | null
  /** Stable catalog slug for Stylebook UI routes when the workspace resolves a Stylebook. */
  workspace_stylebook_slug?: string | null
}

export interface SlowestFlowStat {
  graph_id: string
  flow_name: string
  avg_ms: number
}

export interface TopFlowByCostStat {
  graph_id: string
  flow_name: string
  avg_estimated_cost: string | number
}

export interface ProjectStats {
  total_runs: number
  articles_processed: number
  /** Runs with status ``succeeded``. */
  runs_succeeded: number
  /** Runs still ``pending`` or ``running``. */
  runs_in_progress: number
  /** Runs with status ``failed`` (includes cancelled runs). */
  runs_failed: number
  avg_duration_ms_per_run: number | null
  min_duration_ms_per_run?: number | null
  max_duration_ms_per_run?: number | null
  avg_duration_ms_per_item: number | null
  slowest_flows?: SlowestFlowStat[]
  /** Mean tracked LLM spend per succeeded run. */
  avg_estimated_ai_cost_per_run?: string | number | null
  top_flows_by_cost?: TopFlowByCostStat[]
  avg_estimated_ai_cost_currency?: string | null
  avg_estimated_ai_cost_incomplete?: boolean
}

export interface GraphSummary {
  id: string
  name: string
  description: string
  public_run_enabled: boolean
  project_id: number
  created_at: string
}

export interface Graph extends GraphSummary {
  spec: {
    name: string
    nodes: Array<{
      id: string
      type: string
      params: Record<string, unknown>
      position?: { x: number; y: number }
    }>
    edges?: Array<{
      source: string
      target: string
      sourceHandle?: string | null
      targetHandle?: string | null
    }>
  }
  created_at: string
}

export interface AgateTemplate {
  id: string
  name: string
  description?: string | null
  category?: string | null
}

export interface ProcessedItemSummary {
  id: number
  run_id: string
  /** True when this row is UI-only (no ``agate_processed_item`` row); run output lives on the run. */
  synthetic?: boolean
  source_file: string | null
  input_preview?: string | null
  status: 'pending' | 'running' | 'succeeded' | 'failed' | 'timed_out' | 'skipped'
  error: string | null
  created_at: string
  updated_at: string
  started_at?: string | null
  duration_ms?: number | null
  output_s3_bucket?: string | null
  output_s3_key?: string | null
  input_article_id?: number | null
  input_headline?: string | null
  current_node_types?: string[] | null
  is_array_splitter_item?: boolean
  /** LiteLLM-derived estimated dollar total for this item’s tracked model calls. */
  estimated_ai_cost?: number
  estimated_ai_cost_incomplete?: boolean
  estimated_ai_cost_currency?: string
}

/** Resolved article text for processed item verification (see API docs). */
export interface ArticleContext {
  article_id?: number | null
  headline?: string | null
  body: string
  resolution: 'substrate' | 'inline_fallback' | 'none'
  reason?: string | null
}

export interface ProcessedItem {
  id: number
  run_id: string
  synthetic?: boolean
  source_file: string | null
  input_preview?: string | null
  input: Record<string, unknown>
  output: Record<string, unknown> | null
  node_outputs: Record<string, unknown> | null
  node_logs: Record<string, string[]> | null
  status: 'pending' | 'running' | 'succeeded' | 'failed' | 'timed_out' | 'skipped'
  error: string | null
  created_at: string
  updated_at: string
  started_at?: string | null
  duration_ms?: number | null
  estimated_ai_cost?: number
  estimated_ai_cost_incomplete?: boolean
  estimated_ai_cost_currency?: string
  /** Human review overlay (mutable); model output stays in ``output`` / ``node_outputs``. */
  overlay?: Record<string, unknown> | null
  /** Optimistic concurrency for ``patchProcessedItemOverlay`` (``If-Match``). */
  overlay_version?: number
  /** Merged model + overlay location lane (see API docs). */
  merged_locations?: Array<Record<string, unknown>>
  /** Merged model + overlay people lane (see API docs). */
  merged_people?: Array<Record<string, unknown>>
  /** Merged model + overlay organizations lane (see API docs). */
  merged_organizations?: Array<Record<string, unknown>>
  /** Overlay patches whose anchor no longer exists in model output. */
  stale_overlay_entries?: Array<Record<string, unknown>>
  stale_people_overlay_entries?: Array<Record<string, unknown>>
  stale_organizations_overlay_entries?: Array<Record<string, unknown>>
  /** Materialized model output + overlay for JSON export; absent when no review saved. */
  reviewed_output?: Record<string, unknown> | null
  article_context?: ArticleContext
  /** Compact semantic search indexing status from Backfield Output. */
  semantic_indexing?: ProcessedItemSemanticIndexing
  /** Compact article text embedding status from Embed Text. */
  article_embedding?: ProcessedItemArticleEmbedding
  /** Persisted article metadata tags for Meta review. */
  article_meta?: ProcessedItemArticleMetaRow[]
  /** Compact automatic connections status from Backfield Output. */
  connections?: ProcessedItemConnections
  node_timings?: ProcessedItemNodeTiming[]
}

export interface ProcessedItemNodeTiming {
  node_id: string
  node_type: string
  elapsed_ms: number
}

export interface Run {
  id: string
  graph_id: string
  project_id: number
  status: 'pending' | 'running' | 'completed' | 'completed_with_errors'
  created_at: string
  updated_at: string
  total_items: number
  pending_items: number
  running_items: number
  succeeded_items: number
  failed_items: number
  /** Run-level failure message from the API (``error_message``), when present. */
  error?: string | null
  items?: ProcessedItemSummary[] | null
  node_outputs?: Record<string, unknown> | null
  /** When there are no batch rows, LLM cost for the whole run (``processed_item_id`` null on call rows). */
  whole_run_ai_cost_estimate?: number
  whole_run_ai_cost_incomplete?: boolean
  whole_run_ai_cost_currency?: string
  /** Sum of tracked LLM spend for this run (when provided by the API). */
  estimated_ai_cost_total?: number
  estimated_ai_cost_total_incomplete?: boolean
  /** Pinned flow spec JSON captured when the run started (when available). */
  graph_spec_snapshot_json?: string | null
  /** True when the saved flow differs from the pinned snapshot; null when no snapshot exists. */
  flow_changed_since_run?: boolean | null
}

export interface ApiKey {
  key_name: string
  created_at: string
  updated_at: string
}

export interface ApiKeyCreate {
  key_name: string
  value: string
}

export interface GraphCreate {
  name: string
  description?: string
  public_run_enabled?: boolean
  project_id: number
  spec: {
    name: string
    nodes: Array<{
      id: string
      type: string
      params: Record<string, unknown>
      position?: { x: number; y: number }
    }>
    edges?: Array<{
      source: string
      target: string
      sourceHandle?: string | null
      targetHandle?: string | null
    }>
  }
}

export interface RunCreate {
  input?: Record<string, unknown>
  /** Legacy compatibility flag; saved-data policy now lives on Backfield Output. */
  replace_article_geography_on_persist?: boolean
}

export interface ProjectCreate {
  name: string
  slug?: string
  workspace_id?: number | null
}

export interface ProjectUpdate {
  name?: string
  slug?: string | null
  system_prompt?: string | null
}

interface RawGraph {
  id: string
  name: string
  description?: string | null
  public_run_enabled?: boolean | null
  project_id: number
  spec?: Graph['spec']
  created_at: string
}

export interface ListGraphsOptions {
  projectId?: number
  includeSpec?: boolean
}

export interface ListRunsOptions {
  projectId?: number
  limit?: number
  offset?: number
  includeResult?: boolean
  includeGraphSpecSnapshot?: boolean
}

export interface ListProcessedItemsOptions {
  limit?: number
  offset?: number
  sort?: 'id' | 'source' | 'status' | 'duration' | 'estimated_cost' | 'created_at'
  direction?: 'asc' | 'desc'
}

interface RawProcessedItem {
  id: number
  run_id: string
  source_file: string | null
  input_preview?: string | null
  status: string
  error_message: string | null
  created_at: string
  updated_at: string
  started_at?: string | null
  duration_ms?: number | null
  estimated_ai_cost?: string | number | null
  estimated_ai_cost_incomplete?: boolean
  estimated_ai_cost_currency?: string | null
}

interface RawRun {
  id: string
  graph_id: string
  project_id: number
  status: string
  result?: unknown
  error_message?: string | null
  created_at: string
  updated_at: string
  total_items?: number
  pending_items?: number
  running_items?: number
  succeeded_items?: number
  failed_items?: number
  processed_items?: RawProcessedItem[] | null
  whole_run_ai_cost_estimate?: string | number | null
  whole_run_ai_cost_incomplete?: boolean
  whole_run_ai_cost_currency?: string | null
  estimated_ai_cost_total?: string | number | null
  estimated_ai_cost_total_incomplete?: boolean
  graph_spec_snapshot_json?: string | null
  flow_changed_since_run?: boolean | null
}

interface RawRunStatus {
  id: string
  graph_id: string
  project_id: number
  status: string
  error_message?: string | null
  created_at: string
  updated_at: string
  total_items: number
  pending_items: number
  running_items: number
  succeeded_items: number
  failed_items: number
  estimated_ai_cost_total?: string | number | null
  estimated_ai_cost_total_incomplete?: boolean
  graph_spec_snapshot_json?: string | null
  flow_changed_since_run?: boolean | null
}

interface RawProcessedItemsPage {
  run_id: string
  total: number
  limit: number
  offset: number
  sort: string
  direction: 'asc' | 'desc'
  items: RawProcessedItem[]
}

export interface ProcessedItemsPage {
  run_id: string
  total: number
  limit: number
  offset: number
  sort: string
  direction: 'asc' | 'desc'
  items: ProcessedItemSummary[]
}

function _parseCostAmount(v: unknown): number {
  if (v === null || v === undefined) return 0
  if (typeof v === 'number' && !Number.isNaN(v)) return v
  const n = Number(v)
  return Number.isNaN(n) ? 0 : n
}

function _currencyFromRaw(v: unknown, fallback: string): string {
  return typeof v === 'string' && v.trim() ? v.trim().toUpperCase() : fallback
}

function normalizeGraphSummary(raw: RawGraph): GraphSummary {
  return {
    id: raw.id,
    name: raw.name,
    description: typeof raw.description === 'string' ? raw.description : '',
    public_run_enabled: Boolean(raw.public_run_enabled),
    project_id: raw.project_id,
    created_at: raw.created_at,
  }
}

function normalizeGraph(raw: RawGraph): Graph {
  if (!raw.spec) {
    throw new Error(`Graph ${raw.id} is missing spec`)
  }
  return {
    ...normalizeGraphSummary(raw),
    spec: raw.spec,
  }
}

function mapRunStatus(
  s: string
): 'pending' | 'running' | 'completed' | 'completed_with_errors' {
  if (s === 'pending') return 'pending'
  if (s === 'running') return 'running'
  if (s === 'succeeded') return 'completed'
  if (s === 'failed') return 'completed_with_errors'
  return 'completed_with_errors'
}

function _mapDbProcessedItem(row: RawProcessedItem): ProcessedItemSummary {
  const st = row.status
  const uiStatus: ProcessedItemSummary['status'] =
    st === 'skipped'
      ? 'skipped'
      : st === 'pending' ||
          st === 'running' ||
          st === 'succeeded' ||
          st === 'failed' ||
          st === 'timed_out'
        ? st
        : 'pending'
  const cur = _currencyFromRaw(row.estimated_ai_cost_currency, 'USD')
  return {
    id: row.id,
    run_id: row.run_id,
    source_file: row.source_file,
    input_preview: row.input_preview ?? null,
    status: uiStatus,
    error: row.error_message ?? null,
    created_at: row.created_at,
    updated_at: row.updated_at,
    started_at: row.started_at ?? null,
    duration_ms:
      typeof row.duration_ms === 'number' && !Number.isNaN(row.duration_ms)
        ? row.duration_ms
        : null,
    output_s3_bucket: null,
    output_s3_key: null,
    input_article_id: null,
    input_headline: null,
    current_node_types: null,
    is_array_splitter_item: false,
    estimated_ai_cost: _parseCostAmount(row.estimated_ai_cost),
    estimated_ai_cost_incomplete: Boolean(row.estimated_ai_cost_incomplete),
    estimated_ai_cost_currency: cur,
  }
}

function _syntheticWholeRunItem(
  raw: RawRun,
  status: ProcessedItemSummary['status'],
  {
    estimated_ai_cost,
    estimated_ai_cost_incomplete,
    estimated_ai_cost_currency,
  }: {
    estimated_ai_cost: number
    estimated_ai_cost_incomplete: boolean
    estimated_ai_cost_currency: string
  },
): ProcessedItemSummary {
  return {
    id: 1,
    run_id: raw.id,
    synthetic: true,
    source_file: null,
    input_preview: null,
    status,
    error: status === 'failed' ? raw.error_message || 'failed' : null,
    created_at: raw.created_at,
    updated_at: raw.created_at,
    output_s3_bucket: null,
    output_s3_key: null,
    input_article_id: null,
    input_headline: null,
    current_node_types: null,
    is_array_splitter_item: false,
    estimated_ai_cost,
    estimated_ai_cost_incomplete,
    estimated_ai_cost_currency,
  }
}

function normalizeRun(raw: RawRun): Run {
  const st = mapRunStatus(raw.status)
  const outputs =
    raw.result && typeof raw.result === 'object' && !Array.isArray(raw.result)
      ? (raw.result as Record<string, unknown>)
      : null

  const wrEst = _parseCostAmount(raw.whole_run_ai_cost_estimate)
  const wrInc = Boolean(raw.whole_run_ai_cost_incomplete)
  const wrCur = _currencyFromRaw(raw.whole_run_ai_cost_currency, 'USD')

  let items: ProcessedItemSummary[] = []
  if (raw.processed_items && raw.processed_items.length > 0) {
    items = raw.processed_items.map(_mapDbProcessedItem)
  } else if (st === 'pending') {
    items = [
      _syntheticWholeRunItem(raw, 'pending', {
        estimated_ai_cost: wrEst,
        estimated_ai_cost_incomplete: wrInc,
        estimated_ai_cost_currency: wrCur,
      }),
    ]
  } else if (st === 'running') {
    items = [
      _syntheticWholeRunItem(raw, 'running', {
        estimated_ai_cost: wrEst,
        estimated_ai_cost_incomplete: wrInc,
        estimated_ai_cost_currency: wrCur,
      }),
    ]
  } else if (st === 'completed' && outputs) {
    items = [
      _syntheticWholeRunItem(raw, 'succeeded', {
        estimated_ai_cost: wrEst,
        estimated_ai_cost_incomplete: wrInc,
        estimated_ai_cost_currency: wrCur,
      }),
    ]
  } else if (st === 'completed_with_errors') {
    items = [
      _syntheticWholeRunItem(raw, 'failed', {
        estimated_ai_cost: wrEst,
        estimated_ai_cost_incomplete: wrInc,
        estimated_ai_cost_currency: wrCur,
      }),
    ]
  }

  const succeeded = items.filter((i) => i.status === 'succeeded').length
  const failed = items.filter((i) => i.status === 'failed' || i.status === 'timed_out').length
  const pending_items = items.filter((i) => i.status === 'pending').length
  const running_items = items.filter((i) => i.status === 'running').length
  const hasServerItemCounts =
    typeof raw.total_items === 'number' &&
    typeof raw.pending_items === 'number' &&
    typeof raw.running_items === 'number' &&
    typeof raw.succeeded_items === 'number' &&
    typeof raw.failed_items === 'number'

  const hasTotalAggregate =
    raw.estimated_ai_cost_total !== undefined && raw.estimated_ai_cost_total !== null

  return {
    id: raw.id,
    graph_id: raw.graph_id,
    project_id: raw.project_id,
    status: st,
    created_at: raw.created_at,
    updated_at: raw.updated_at,
    total_items: hasServerItemCounts ? (raw.total_items ?? 0) : items.length,
    pending_items: hasServerItemCounts ? (raw.pending_items ?? 0) : pending_items,
    running_items: hasServerItemCounts ? (raw.running_items ?? 0) : running_items,
    succeeded_items: hasServerItemCounts ? (raw.succeeded_items ?? 0) : succeeded,
    failed_items: hasServerItemCounts ? (raw.failed_items ?? 0) : failed,
    error: raw.error_message ?? null,
    items,
    node_outputs: outputs,
    whole_run_ai_cost_estimate: wrEst,
    whole_run_ai_cost_incomplete: wrInc,
    whole_run_ai_cost_currency: wrCur,
    ...(hasTotalAggregate
      ? {
          estimated_ai_cost_total: _parseCostAmount(raw.estimated_ai_cost_total),
          estimated_ai_cost_total_incomplete: Boolean(raw.estimated_ai_cost_total_incomplete),
        }
      : {}),
    ...(raw.graph_spec_snapshot_json != null
      ? { graph_spec_snapshot_json: raw.graph_spec_snapshot_json }
      : {}),
    ...(raw.flow_changed_since_run === true || raw.flow_changed_since_run === false
      ? { flow_changed_since_run: raw.flow_changed_since_run }
      : {}),
  }
}

function normalizeRunStatus(raw: RawRunStatus): Run {
  return {
    id: raw.id,
    graph_id: raw.graph_id,
    project_id: raw.project_id,
    status: mapRunStatus(raw.status),
    created_at: raw.created_at,
    updated_at: raw.updated_at,
    total_items: raw.total_items,
    pending_items: raw.pending_items,
    running_items: raw.running_items,
    succeeded_items: raw.succeeded_items,
    failed_items: raw.failed_items,
    error: raw.error_message ?? null,
    items: null,
    node_outputs: null,
    estimated_ai_cost_total: _parseCostAmount(raw.estimated_ai_cost_total),
    estimated_ai_cost_total_incomplete: Boolean(raw.estimated_ai_cost_total_incomplete),
    ...(raw.graph_spec_snapshot_json != null
      ? { graph_spec_snapshot_json: raw.graph_spec_snapshot_json }
      : {}),
    ...(raw.flow_changed_since_run === true || raw.flow_changed_since_run === false
      ? { flow_changed_since_run: raw.flow_changed_since_run }
      : {}),
  }
}

async function fetchAPI(path: string, options?: RequestInit): Promise<unknown> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  })

  if (response.status === 401) {
    throw new Error('Unauthorized')
  }

  if (!response.ok) {
    const error = await response.text()
    throw new Error(`API error: ${response.status} - ${error}`)
  }

  if (response.status === 204) {
    return null
  }

  return response.json()
}

export async function createGraph(data: GraphCreate): Promise<Graph> {
  const raw = (await fetchAPI('/graphs', {
    method: 'POST',
    body: JSON.stringify({
      name: data.name,
      description: data.description ?? '',
      public_run_enabled: Boolean(data.public_run_enabled),
      project_id: data.project_id,
      spec: data.spec,
    }),
  })) as RawGraph
  return normalizeGraph(raw)
}

export async function listGraphs(
  options: ListGraphsOptions & { includeSpec: false },
): Promise<GraphSummary[]>
export async function listGraphs(options?: ListGraphsOptions): Promise<Graph[]>
export async function listGraphs(options: ListGraphsOptions = {}): Promise<Graph[] | GraphSummary[]> {
  const params = new URLSearchParams()
  if (options.projectId != null) {
    params.set('project_id', String(options.projectId))
  }
  if (options.includeSpec === false) {
    params.set('include_spec', 'false')
  }
  const query = params.toString()
  const raw = (await fetchAPI(`/graphs${query ? `?${query}` : ''}`)) as RawGraph[]
  if (options.includeSpec === false) {
    return raw.map(normalizeGraphSummary)
  }
  return raw.map(normalizeGraph)
}

export async function listGraphSummaries(projectId?: number): Promise<GraphSummary[]> {
  return listGraphs({ projectId, includeSpec: false })
}

export async function getGraph(id: string | number): Promise<Graph> {
  const raw = (await fetchAPI(`/graphs/${id}`)) as RawGraph
  return normalizeGraph(raw)
}

export async function updateGraph(id: string | number, data: GraphCreate): Promise<Graph> {
  const raw = (await fetchAPI(`/graphs/${id}`, {
    method: 'PUT',
    body: JSON.stringify({
      name: data.name,
      description: data.description ?? '',
      public_run_enabled: Boolean(data.public_run_enabled),
      project_id: data.project_id,
      spec: data.spec,
    }),
  })) as RawGraph
  return normalizeGraph(raw)
}

export async function deleteGraph(id: string | number): Promise<void> {
  await fetchAPI(`/graphs/${id}`, { method: 'DELETE' })
}

export async function createRun(graphId: string | number, data: RunCreate = {}): Promise<Run> {
  const body: Record<string, unknown> = { graph_id: String(graphId) }
  if (data.replace_article_geography_on_persist) {
    body.replace_article_geography_on_persist = true
  }
  const raw = (await fetchAPI('/runs', {
    method: 'POST',
    body: JSON.stringify(body),
  })) as RawRun
  return normalizeRun(raw)
}

export async function replayRun(runId: string): Promise<Run> {
  const raw = (await fetchAPI(`/runs/${runId}/replay`, {
    method: 'POST',
  })) as RawRun
  return normalizeRun(raw)
}

export async function listRuns(options: ListRunsOptions = {}): Promise<Run[]> {
  const params = new URLSearchParams()
  if (options.projectId != null) {
    params.set('project_id', String(options.projectId))
  }
  if (options.limit != null) {
    params.set('limit', String(options.limit))
  }
  if (options.offset != null) {
    params.set('offset', String(options.offset))
  }
  if (options.includeResult === false) {
    params.set('include_result', 'false')
  }
  if (options.includeGraphSpecSnapshot === false) {
    params.set('include_graph_spec_snapshot', 'false')
  }
  const query = params.toString()
  const raw = (await fetchAPI(`/runs${query ? `?${query}` : ''}`)) as RawRun[]
  return raw.map(normalizeRun)
}

export async function getRun(id: string | number): Promise<Run> {
  const raw = (await fetchAPI(`/runs/${id}`)) as RawRun
  return normalizeRun(raw)
}

export async function getRunStatus(id: string | number): Promise<Run> {
  const raw = (await fetchAPI(`/runs/${id}/status`)) as RawRunStatus
  return normalizeRunStatus(raw)
}

export async function getRunProcessedItemsPage(
  runId: string | number,
  options: ListProcessedItemsOptions = {},
): Promise<ProcessedItemsPage> {
  const params = new URLSearchParams()
  if (options.limit != null) {
    params.set('limit', String(options.limit))
  }
  if (options.offset != null) {
    params.set('offset', String(options.offset))
  }
  if (options.sort) {
    params.set('sort', options.sort)
  }
  if (options.direction) {
    params.set('direction', options.direction)
  }
  const query = params.toString()
  const raw = (await fetchAPI(
    `/runs/${runId}/items${query ? `?${query}` : ''}`,
  )) as RawProcessedItemsPage
  return {
    ...raw,
    items: raw.items.map(_mapDbProcessedItem),
  }
}

export interface RunEstimatedAiCost {
  run_id: string
  currency: string
  estimated_total: string
  incomplete_estimate: boolean
  attempt_count: number
  node_breakdown: Array<{
    node_id: string | null
    node_type?: string | null
    estimated_total: string
  }>
}

export async function getRunEstimatedAiCost(runId: string): Promise<RunEstimatedAiCost> {
  return fetchAPI(`/runs/${runId}/estimated-ai-cost`) as Promise<RunEstimatedAiCost>
}

export interface ProjectEstimatedAiCost {
  project_id: number
  currency: string
  estimated_total: string
  incomplete_estimate: boolean
  attempt_count: number
  model_breakdown: Array<{ provider_model_id: string; estimated_total: string }>
}

export async function getProjectEstimatedAiCost(
  projectId: number,
): Promise<ProjectEstimatedAiCost> {
  return fetchAPI(`/projects/${projectId}/estimated-ai-cost`) as Promise<ProjectEstimatedAiCost>
}

interface RawProcessedItemDetail {
  id: number
  run_id: string
  synthetic?: boolean
  source_file: string | null
  input_preview?: string | null
  input: Record<string, unknown>
  output: Record<string, unknown> | null
  node_outputs: Record<string, unknown> | null
  node_logs: Record<string, string[]> | null
  status: string
  error: string | null
  created_at: string
  updated_at: string
  started_at?: string | null
  duration_ms?: number | null
  estimated_ai_cost?: string | number | null
  estimated_ai_cost_incomplete?: boolean
  estimated_ai_cost_currency?: string | null
  overlay?: Record<string, unknown> | null
  overlay_version?: number
  reviewed_output?: Record<string, unknown> | null
  merged_locations?: Array<Record<string, unknown>>
  merged_people?: Array<Record<string, unknown>>
  merged_organizations?: Array<Record<string, unknown>>
  stale_overlay_entries?: Array<Record<string, unknown>>
  stale_people_overlay_entries?: Array<Record<string, unknown>>
  stale_organizations_overlay_entries?: Array<Record<string, unknown>>
  article_context?: unknown
  semantic_indexing?: unknown
  article_embedding?: unknown
  article_meta?: unknown
  connections?: unknown
  node_timings?: Array<{ node_id: string; node_type: string; elapsed_ms: number }>
}

function _normalizeArticleContext(raw: unknown): ArticleContext {
  if (!raw || typeof raw !== 'object') {
    return {
      article_id: null,
      headline: null,
      body: '',
      resolution: 'none',
      reason: null,
    }
  }
  const o = raw as Record<string, unknown>
  const res = o.resolution
  const resolution: ArticleContext['resolution'] =
    res === 'substrate' || res === 'inline_fallback' || res === 'none' ? res : 'none'
  const aid = o.article_id
  const articleId =
    typeof aid === 'number' && !Number.isNaN(aid)
      ? aid
      : typeof aid === 'string'
        ? Number.parseInt(aid, 10) || null
        : null
  const hl = o.headline
  const headline = typeof hl === 'string' ? hl : null
  const bodyRaw = o.body
  const body = typeof bodyRaw === 'string' ? bodyRaw : ''
  const reasonRaw = o.reason
  const reason = typeof reasonRaw === 'string' ? reasonRaw : null
  return {
    article_id: articleId,
    headline,
    body,
    resolution,
    reason,
  }
}

function normalizeProcessedItemDetail(raw: RawProcessedItemDetail): ProcessedItem {
  const st = raw.status
  const uiStatus: ProcessedItem['status'] =
    st === 'skipped'
      ? 'skipped'
      : st === 'pending' ||
          st === 'running' ||
          st === 'succeeded' ||
          st === 'failed' ||
          st === 'timed_out'
        ? st
        : 'pending'
  const cur = _currencyFromRaw(raw.estimated_ai_cost_currency, 'USD')
  const overlayVersion =
    typeof raw.overlay_version === 'number' && !Number.isNaN(raw.overlay_version)
      ? raw.overlay_version
      : typeof raw.overlay_version === 'string'
        ? Number.parseInt(raw.overlay_version, 10) || 0
        : 0
  return {
    id: raw.id,
    run_id: raw.run_id,
    synthetic: Boolean(raw.synthetic),
    source_file: raw.source_file,
    input_preview: raw.input_preview ?? null,
    input: raw.input,
    output: raw.output,
    node_outputs: raw.node_outputs,
    node_logs: raw.node_logs,
    status: uiStatus,
    error: raw.error,
    created_at: raw.created_at,
    updated_at: raw.updated_at,
    started_at: raw.started_at ?? null,
    duration_ms:
      typeof raw.duration_ms === 'number' && !Number.isNaN(raw.duration_ms)
        ? raw.duration_ms
        : null,
    estimated_ai_cost: _parseCostAmount(raw.estimated_ai_cost),
    estimated_ai_cost_incomplete: Boolean(raw.estimated_ai_cost_incomplete),
    estimated_ai_cost_currency: cur,
    overlay: raw.overlay ?? null,
    overlay_version: overlayVersion,
    merged_locations: Array.isArray(raw.merged_locations) ? raw.merged_locations : [],
    merged_people: Array.isArray(raw.merged_people) ? raw.merged_people : [],
    merged_organizations: Array.isArray(raw.merged_organizations)
      ? raw.merged_organizations
      : [],
    stale_overlay_entries: Array.isArray(raw.stale_overlay_entries)
      ? raw.stale_overlay_entries
      : [],
    stale_people_overlay_entries: Array.isArray(raw.stale_people_overlay_entries)
      ? raw.stale_people_overlay_entries
      : [],
    stale_organizations_overlay_entries: Array.isArray(raw.stale_organizations_overlay_entries)
      ? raw.stale_organizations_overlay_entries
      : [],
    reviewed_output:
      raw.reviewed_output && typeof raw.reviewed_output === 'object'
        ? raw.reviewed_output
        : null,
    article_context: _normalizeArticleContext(raw.article_context),
    semantic_indexing: normalizeProcessedItemSemanticIndexing(raw.semantic_indexing),
    article_embedding: normalizeProcessedItemArticleEmbedding(raw.article_embedding),
    article_meta: normalizeProcessedItemArticleMetaRows(raw.article_meta),
    connections: normalizeProcessedItemConnections(raw.connections),
    node_timings: Array.isArray(raw.node_timings)
      ? raw.node_timings.map((row) => ({
          node_id: String(row.node_id),
          node_type: String(row.node_type),
          elapsed_ms: Number(row.elapsed_ms),
        }))
      : [],
  }
}

export async function getProcessedItem(
  runId: string | number,
  itemId: number
): Promise<ProcessedItem> {
  const raw = (await fetchAPI(`/runs/${runId}/items/${itemId}`)) as RawProcessedItemDetail
  return normalizeProcessedItemDetail(raw)
}

export async function patchProcessedItemOverlay(
  runId: string | number,
  itemId: number,
  overlay: Record<string, unknown>,
  ifMatchVersion: number
): Promise<ProcessedItem> {
  const raw = (await fetchAPI(`/runs/${runId}/items/${itemId}`, {
    method: 'PATCH',
    headers: {
      'If-Match': `"${ifMatchVersion}"`,
    },
    body: JSON.stringify({ overlay }),
  })) as RawProcessedItemDetail
  return normalizeProcessedItemDetail(raw)
}

export async function createProcessedItemArticleMeta(
  runId: string | number,
  itemId: number,
  body: {
    meta_type: string
    category: string
    rationale?: string
    confidence?: number
    prompt_preset?: string
  },
  ifMatchVersion: number,
): Promise<ProcessedItem> {
  const raw = (await fetchAPI(`/runs/${runId}/items/${itemId}/article-meta`, {
    method: 'POST',
    headers: {
      'If-Match': `"${ifMatchVersion}"`,
    },
    body: JSON.stringify(body),
  })) as RawProcessedItemDetail
  return normalizeProcessedItemDetail(raw)
}

export async function patchProcessedItemArticleMetaCategory(
  runId: string | number,
  itemId: number,
  metaRowId: number,
  category: string,
  ifMatchVersion: number,
): Promise<ProcessedItem> {
  const raw = (await fetchAPI(`/runs/${runId}/items/${itemId}/article-meta/${metaRowId}`, {
    method: 'PATCH',
    headers: {
      'If-Match': `"${ifMatchVersion}"`,
    },
    body: JSON.stringify({ category }),
  })) as RawProcessedItemDetail
  return normalizeProcessedItemDetail(raw)
}

export async function deleteProcessedItemArticleMeta(
  runId: string | number,
  itemId: number,
  metaRowId: number,
  ifMatchVersion: number,
): Promise<ProcessedItem> {
  const raw = (await fetchAPI(`/runs/${runId}/items/${itemId}/article-meta/${metaRowId}`, {
    method: 'DELETE',
    headers: {
      'If-Match': `"${ifMatchVersion}"`,
    },
  })) as RawProcessedItemDetail
  return normalizeProcessedItemDetail(raw)
}

export interface RerunItemResponse {
  item_id: number
  run_id: string
  status: string
  message: string
}

export async function rerunProcessedItem(
  runId: string | number,
  itemId: number
): Promise<RerunItemResponse> {
  return fetchAPI(`/runs/${runId}/items/${itemId}/rerun`, {
    method: 'POST',
  }) as Promise<RerunItemResponse>
}

export interface S3SyncItemResponse {
  item_id: number
  run_id: string
  message: string
}

/** Queue a worker upload that overwrites the story's S3 Output file with current JSON. */
export async function syncProcessedItemS3Output(
  runId: string | number,
  itemId: number
): Promise<S3SyncItemResponse> {
  return fetchAPI(`/runs/${runId}/items/${itemId}/s3-sync`, {
    method: 'POST',
  }) as Promise<S3SyncItemResponse>
}

export async function cancelRun(runId: string | number): Promise<Run> {
  const raw = (await fetchAPI(`/runs/${runId}/cancel`, {
    method: 'POST',
  })) as RawRunStatus
  return normalizeRunStatus(raw)
}

export async function checkHealth(): Promise<{ ok: boolean }> {
  return fetchAPI('/health') as Promise<{ ok: boolean }>
}

export async function createProject(data: ProjectCreate): Promise<Project> {
  return fetchAPI('/projects', {
    method: 'POST',
    body: JSON.stringify({
      name: data.name,
      slug: data.slug,
      workspace_id: data.workspace_id ?? null,
    }),
  }) as Promise<Project>
}

export async function listProjects(): Promise<Project[]> {
  return fetchAPI('/projects') as Promise<Project[]>
}

export async function getProject(id: number): Promise<Project> {
  return fetchAPI(`/projects/${id}`) as Promise<Project>
}

export async function getProjectBySlug(slug: string): Promise<Project> {
  return fetchAPI(`/projects/by-slug/${encodeURIComponent(slug)}`) as Promise<Project>
}

export async function getProjectStats(projectId: number): Promise<ProjectStats> {
  return fetchAPI(`/projects/${projectId}/stats`) as Promise<ProjectStats>
}

export async function getProjectStatsBySlug(slug: string): Promise<ProjectStats> {
  return fetchAPI(
    `/projects/by-slug/${encodeURIComponent(slug)}/stats`
  ) as Promise<ProjectStats>
}

export async function updateProject(id: number, data: ProjectUpdate): Promise<Project> {
  return fetchAPI(`/projects/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  }) as Promise<Project>
}

export async function deleteProject(id: number): Promise<void> {
  await fetchAPI(`/projects/${id}`, { method: 'DELETE' })
}

export async function listTemplates(): Promise<AgateTemplate[]> {
  return fetchAPI('/templates') as Promise<AgateTemplate[]>
}

export async function instantiateTemplate(
  templateId: string,
  body: { project_id: number; name?: string }
): Promise<Graph> {
  const raw = (await fetchAPI(`/templates/${templateId}/instantiate`, {
    method: 'POST',
    body: JSON.stringify(body),
  })) as RawGraph
  return normalizeGraph(raw)
}

export async function listProjectApiKeys(projectId: number): Promise<ApiKey[]> {
  const rows = (await fetchAPI(`/projects/${projectId}/secrets`)) as Array<{
    key_name: string
    created_at: string
    updated_at: string
  }>
  return rows.map((r) => ({
    key_name: r.key_name,
    created_at: r.created_at,
    updated_at: r.updated_at,
  }))
}

export async function setProjectApiKey(
  projectId: number,
  data: ApiKeyCreate
): Promise<ApiKey> {
  return fetchAPI(`/projects/${projectId}/secrets/${encodeURIComponent(data.key_name)}`, {
    method: 'PUT',
    body: JSON.stringify({ value: data.value }),
  }) as Promise<ApiKey>
}

export async function deleteProjectApiKey(projectId: number, keyName: string): Promise<void> {
  await fetchAPI(`/projects/${projectId}/secrets/${encodeURIComponent(keyName)}`, {
    method: 'DELETE',
  })
}
