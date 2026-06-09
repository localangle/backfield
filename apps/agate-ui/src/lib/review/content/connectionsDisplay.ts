export type ProcessedItemConnectionsStatus =
  | 'disabled'
  | 'ineligible'
  | 'pending'
  | 'running'
  | 'succeeded'
  | 'failed'

export interface ProcessedItemConnectionEdge {
  from_display_name: string
  to_display_name: string
  nature: string
  confidence: number | null
}

export interface ProcessedItemConnections {
  status: ProcessedItemConnectionsStatus
  enabled: boolean
  created_count: number
  edges: ProcessedItemConnectionEdge[]
  error: string | null
}

const DEFAULT_CONNECTIONS: ProcessedItemConnections = {
  status: 'disabled',
  enabled: false,
  created_count: 0,
  edges: [],
  error: null,
}

export function normalizeProcessedItemConnections(raw: unknown): ProcessedItemConnections {
  if (!raw || typeof raw !== 'object') {
    return DEFAULT_CONNECTIONS
  }
  const o = raw as Record<string, unknown>
  const statusRaw = o.status
  const status: ProcessedItemConnectionsStatus =
    statusRaw === 'disabled' ||
    statusRaw === 'ineligible' ||
    statusRaw === 'pending' ||
    statusRaw === 'running' ||
    statusRaw === 'succeeded' ||
    statusRaw === 'failed'
      ? statusRaw
      : 'disabled'
  const edgesRaw = o.edges
  const edges: ProcessedItemConnectionEdge[] = []
  if (Array.isArray(edgesRaw)) {
    for (const edge of edgesRaw) {
      if (!edge || typeof edge !== 'object') continue
      const row = edge as Record<string, unknown>
      const fromName = typeof row.from_display_name === 'string' ? row.from_display_name.trim() : ''
      const toName = typeof row.to_display_name === 'string' ? row.to_display_name.trim() : ''
      const nature = typeof row.nature === 'string' ? row.nature.trim() : ''
      if (!fromName || !toName || !nature) continue
      const confRaw = row.confidence
      let confidence: number | null = null
      if (typeof confRaw === 'number' && !Number.isNaN(confRaw)) {
        confidence = confRaw
      }
      edges.push({
        from_display_name: fromName,
        to_display_name: toName,
        nature,
        confidence,
      })
    }
  }
  const errorRaw = o.error
  const error = typeof errorRaw === 'string' && errorRaw.trim() ? errorRaw : null
  const createdRaw = o.created_count
  const createdCount =
    typeof createdRaw === 'number' && !Number.isNaN(createdRaw)
      ? Math.max(0, createdRaw)
      : 0
  return {
    status,
    enabled: Boolean(o.enabled),
    created_count: createdCount,
    edges,
    error,
  }
}

export function connectionsStatusLabel(status: ProcessedItemConnectionsStatus): string {
  switch (status) {
    case 'disabled':
      return 'Off'
    case 'ineligible':
      return 'Unavailable'
    case 'pending':
      return 'Waiting'
    case 'running':
      return 'Running'
    case 'succeeded':
      return 'Complete'
    case 'failed':
      return 'Failed'
    default:
      return 'Off'
  }
}

export function formatConnectionsDetail(summary: ProcessedItemConnections): string | null {
  if (summary.status === 'disabled' || summary.status === 'ineligible') {
    return null
  }
  if (summary.status === 'pending' || summary.status === 'running') {
    return 'Automatic connections are still running for this item.'
  }
  if (summary.status === 'failed') {
    return summary.error ?? 'Automatic connections could not finish for this item.'
  }
  if (summary.created_count === 0) {
    return 'No connections created'
  }
  return `${summary.created_count.toLocaleString()} connection${
    summary.created_count === 1 ? '' : 's'
  } created`
}

export function shouldShowConnectionsSummary(
  summary: ProcessedItemConnections | undefined,
): boolean {
  return Boolean(summary && summary.status !== 'disabled')
}

export function getConnectionsStatusColor(status: ProcessedItemConnectionsStatus): string {
  switch (status) {
    case 'succeeded':
      return 'text-green-600 dark:text-green-400'
    case 'failed':
      return 'text-destructive'
    case 'ineligible':
    case 'pending':
    case 'running':
      return 'text-muted-foreground'
    default:
      return 'text-muted-foreground'
  }
}
