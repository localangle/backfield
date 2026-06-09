export type ProcessedItemSemanticIndexingStatus =
  | 'not_enabled'
  | 'pending'
  | 'running'
  | 'succeeded'
  | 'partial'
  | 'failed'

export interface ProcessedItemSemanticIndexing {
  status: ProcessedItemSemanticIndexingStatus
  enabled: boolean
  document_count: number
  indexed_count: number
  pending_count: number
  failed_count: number
  indexed_at?: string | null
  embedding_model?: string | null
  error?: string | null
}

const DEFAULT_SEMANTIC_INDEXING: ProcessedItemSemanticIndexing = {
  status: 'not_enabled',
  enabled: false,
  document_count: 0,
  indexed_count: 0,
  pending_count: 0,
  failed_count: 0,
  indexed_at: null,
  embedding_model: null,
  error: null,
}

export function normalizeProcessedItemSemanticIndexing(
  raw: unknown,
): ProcessedItemSemanticIndexing {
  if (!raw || typeof raw !== 'object') {
    return DEFAULT_SEMANTIC_INDEXING
  }
  const o = raw as Record<string, unknown>
  const statusRaw = o.status
  const status: ProcessedItemSemanticIndexingStatus =
    statusRaw === 'pending' ||
    statusRaw === 'running' ||
    statusRaw === 'succeeded' ||
    statusRaw === 'partial' ||
    statusRaw === 'failed' ||
    statusRaw === 'not_enabled'
      ? statusRaw
      : 'not_enabled'
  const indexedAtRaw = o.indexed_at
  const indexedAt =
    typeof indexedAtRaw === 'string' && indexedAtRaw.trim() ? indexedAtRaw : null
  const modelRaw = o.embedding_model
  const embeddingModel = typeof modelRaw === 'string' && modelRaw.trim() ? modelRaw : null
  const errorRaw = o.error
  const error = typeof errorRaw === 'string' && errorRaw.trim() ? errorRaw : null
  return {
    status,
    enabled: Boolean(o.enabled),
    document_count: _count(o.document_count),
    indexed_count: _count(o.indexed_count),
    pending_count: _count(o.pending_count),
    failed_count: _count(o.failed_count),
    indexed_at: indexedAt,
    embedding_model: embeddingModel,
    error,
  }
}

function _count(value: unknown): number {
  if (typeof value === 'number' && !Number.isNaN(value)) {
    return Math.max(0, value)
  }
  if (typeof value === 'string') {
    const parsed = Number.parseInt(value, 10)
    return Number.isNaN(parsed) ? 0 : Math.max(0, parsed)
  }
  return 0
}

export function semanticIndexingStatusLabel(status: ProcessedItemSemanticIndexingStatus): string {
  switch (status) {
    case 'not_enabled':
      return 'Off'
    case 'pending':
      return 'Waiting'
    case 'running':
      return 'Indexing'
    case 'succeeded':
      return 'Complete'
    case 'partial':
      return 'Partial'
    case 'failed':
      return 'Failed'
    default:
      return 'Off'
  }
}

export function formatSemanticIndexingDetail(
  summary: ProcessedItemSemanticIndexing,
): string | null {
  if (summary.status === 'not_enabled') {
    return null
  }
  if (summary.status === 'pending' || summary.status === 'running') {
    return 'Semantic search is in progress for this item.'
  }
  if (summary.status === 'failed') {
    return summary.error ?? 'Semantic search could not finish for this item.'
  }
  if (summary.indexed_count > 0) {
    return `${summary.indexed_count.toLocaleString()} document${
      summary.indexed_count === 1 ? '' : 's'
    } indexed`
  }
  if (summary.failed_count > 0) {
    return `${summary.failed_count.toLocaleString()} document${
      summary.failed_count === 1 ? '' : 's'
    } failed to index`
  }
  return 'No documents indexed'
}

export function shouldShowSemanticIndexingSummary(
  summary: ProcessedItemSemanticIndexing | undefined,
): boolean {
  return Boolean(summary && summary.status !== 'not_enabled')
}
