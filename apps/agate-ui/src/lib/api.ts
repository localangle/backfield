/**
 * Agate API client — Backfield agate-api.
 */

export const API_BASE =
  import.meta.env.VITE_API_BASE ||
  import.meta.env.VITE_AGATE_API_BASE ||
  import.meta.env.VITE_REWRITE_API_BASE ||
  'http://localhost:8000'

export interface Project {
  id: number
  name: string
  slug: string
  system_prompt?: string
  created_at: string
  updated_at?: string
}

export interface ProjectStats {
  total_runs: number
  articles_processed: number
  avg_duration_ms_per_run: number | null
  avg_duration_ms_per_item: number | null
}

export interface Graph {
  id: string
  name: string
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
  source_file: string | null
  status: 'pending' | 'running' | 'succeeded' | 'failed' | 'timed_out'
  error: string | null
  created_at: string
  updated_at: string
  output_s3_bucket?: string | null
  output_s3_key?: string | null
  input_article_id?: number | null
  input_headline?: string | null
  current_node_types?: string[] | null
  is_array_splitter_item?: boolean
}

export interface ProcessedItem {
  id: number
  run_id: string
  source_file: string | null
  input: Record<string, unknown>
  output: Record<string, unknown> | null
  node_outputs: Record<string, unknown> | null
  node_logs: Record<string, string[]> | null
  status: 'pending' | 'running' | 'succeeded' | 'failed' | 'timed_out'
  error: string | null
  created_at: string
  updated_at: string
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
  items?: ProcessedItemSummary[] | null
  mapbox_api_token?: string | null
  node_outputs?: Record<string, unknown> | null
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
  input: Record<string, unknown>
}

export interface ProjectCreate {
  name: string
  slug?: string
}

export interface ProjectUpdate {
  name?: string
  slug?: string | null
  system_prompt?: string | null
}

interface RawGraph {
  id: string
  name: string
  project_id: number
  spec: Graph['spec']
  created_at: string
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
}

function normalizeGraph(raw: RawGraph): Graph {
  return {
    id: raw.id,
    name: raw.name,
    project_id: raw.project_id,
    spec: raw.spec,
    created_at: raw.created_at,
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

function normalizeRun(raw: RawRun): Run {
  const st = mapRunStatus(raw.status)
  const outputs =
    raw.result && typeof raw.result === 'object' && !Array.isArray(raw.result)
      ? (raw.result as Record<string, unknown>)
      : null

  const items: ProcessedItemSummary[] =
    st === 'completed' && outputs
      ? [
          {
            id: 1,
            run_id: raw.id,
            source_file: null,
            status: 'succeeded',
            error: null,
            created_at: raw.created_at,
            updated_at: raw.created_at,
          },
        ]
      : st === 'completed_with_errors'
        ? [
            {
              id: 1,
              run_id: raw.id,
              source_file: null,
              status: 'failed',
              error: raw.error_message || 'failed',
              created_at: raw.created_at,
              updated_at: raw.created_at,
            },
          ]
        : []

  const succeeded = items.filter((i) => i.status === 'succeeded').length
  const failed = items.filter((i) => i.status === 'failed').length

  return {
    id: raw.id,
    graph_id: raw.graph_id,
    project_id: raw.project_id,
    status: st,
    created_at: raw.created_at,
    updated_at: raw.updated_at,
    total_items: items.length,
    pending_items: raw.status === 'pending' ? 1 : 0,
    running_items: raw.status === 'running' ? 1 : 0,
    succeeded_items: succeeded,
    failed_items: failed,
    items,
    node_outputs: outputs,
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
      project_id: data.project_id,
      spec: data.spec,
    }),
  })) as RawGraph
  return normalizeGraph(raw)
}

export async function listGraphs(): Promise<Graph[]> {
  const raw = (await fetchAPI('/graphs')) as RawGraph[]
  return raw.map(normalizeGraph)
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
      project_id: data.project_id,
      spec: data.spec,
    }),
  })) as RawGraph
  return normalizeGraph(raw)
}

export async function deleteGraph(id: string | number): Promise<void> {
  await fetchAPI(`/graphs/${id}`, { method: 'DELETE' })
}

export async function createRun(graphId: string | number, _data: RunCreate): Promise<Run> {
  const raw = (await fetchAPI('/runs', {
    method: 'POST',
    body: JSON.stringify({ graph_id: String(graphId) }),
  })) as RawRun
  return normalizeRun(raw)
}

export async function listRuns(_limit = 50, _offset = 0): Promise<Run[]> {
  const raw = (await fetchAPI('/runs')) as RawRun[]
  return raw.map(normalizeRun)
}

export async function getRun(id: string | number): Promise<Run> {
  const raw = (await fetchAPI(`/runs/${id}`)) as RawRun
  return normalizeRun(raw)
}

export async function getProcessedItem(
  runId: string | number,
  itemId: number
): Promise<ProcessedItem> {
  const raw = (await fetchAPI(`/runs/${runId}`)) as RawRun
  if (itemId !== 1) {
    throw new Error('Item not found')
  }
  const outputs =
    raw.result && typeof raw.result === 'object' && !Array.isArray(raw.result)
      ? (raw.result as Record<string, unknown>)
      : null
  const now = raw.created_at
  const ok = raw.status === 'succeeded'
  return {
    id: 1,
    run_id: String(runId),
    source_file: null,
    input: {},
    output: outputs as Record<string, unknown> | null,
    node_outputs: outputs,
    node_logs: null,
    status: ok ? 'succeeded' : raw.status === 'failed' ? 'failed' : 'pending',
    error: raw.error_message || null,
    created_at: now,
    updated_at: now,
  }
}

export interface RerunItemResponse {
  item_id: number
  run_id: string
  status: string
  message: string
}

export async function rerunProcessedItem(
  _runId: string | number,
  _itemId: number
): Promise<RerunItemResponse> {
  throw new Error('Rerun is not available in Backfield yet')
}

export async function cancelRun(_runId: string | number): Promise<Run> {
  throw new Error('Cancel run is not available in Backfield yet')
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
