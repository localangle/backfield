export type ProcessedItemArticleEmbeddingStatus =
  | 'not_present'
  | 'pending'
  | 'running'
  | 'succeeded'
  | 'skipped'
  | 'failed'

export interface ProcessedItemArticleEmbedding {
  status: ProcessedItemArticleEmbeddingStatus
  present: boolean
  persisted: boolean
  embedding_model?: string | null
  embedding_dimensions?: number | null
  embedded_at?: string | null
  error?: string | null
}

const DEFAULT_ARTICLE_EMBEDDING: ProcessedItemArticleEmbedding = {
  status: 'not_present',
  present: false,
  persisted: false,
  embedding_model: null,
  embedding_dimensions: null,
  embedded_at: null,
  error: null,
}

export function normalizeProcessedItemArticleEmbedding(
  raw: unknown,
): ProcessedItemArticleEmbedding {
  if (!raw || typeof raw !== 'object') {
    return DEFAULT_ARTICLE_EMBEDDING
  }
  const o = raw as Record<string, unknown>
  const statusRaw = o.status
  const status: ProcessedItemArticleEmbeddingStatus =
    statusRaw === 'pending' ||
    statusRaw === 'running' ||
    statusRaw === 'succeeded' ||
    statusRaw === 'skipped' ||
    statusRaw === 'failed' ||
    statusRaw === 'not_present'
      ? statusRaw
      : 'not_present'
  const modelRaw = o.embedding_model
  const embeddingModel = typeof modelRaw === 'string' && modelRaw.trim() ? modelRaw : null
  const dimsRaw = o.embedding_dimensions
  const embeddingDimensions =
    typeof dimsRaw === 'number' && !Number.isNaN(dimsRaw) ? dimsRaw : null
  const embeddedAtRaw = o.embedded_at
  const embeddedAt =
    typeof embeddedAtRaw === 'string' && embeddedAtRaw.trim() ? embeddedAtRaw : null
  const errorRaw = o.error
  const error = typeof errorRaw === 'string' && errorRaw.trim() ? errorRaw : null
  return {
    status,
    present: Boolean(o.present),
    persisted: Boolean(o.persisted),
    embedding_model: embeddingModel,
    embedding_dimensions: embeddingDimensions,
    embedded_at: embeddedAt,
    error,
  }
}

export function articleEmbeddingStatusLabel(
  status: ProcessedItemArticleEmbeddingStatus,
): string {
  switch (status) {
    case 'not_present':
      return 'None'
    case 'pending':
      return 'Waiting'
    case 'running':
      return 'Embedding'
    case 'succeeded':
      return 'Complete'
    case 'skipped':
      return 'Skipped'
    case 'failed':
      return 'Failed'
    default:
      return 'None'
  }
}

export function formatArticleEmbeddingDetail(
  summary: ProcessedItemArticleEmbedding,
): string | null {
  if (!summary.present || summary.status === 'not_present') {
    return null
  }
  if (summary.status === 'failed') {
    return summary.error ?? 'Article embedding could not be created.'
  }
  if (summary.status === 'skipped') {
    return 'An existing article embedding was kept.'
  }
  const model = summary.embedding_model?.trim()
  const dims = summary.embedding_dimensions
  if (model && dims != null) {
    return `${model} · ${dims.toLocaleString()} dimensions`
  }
  if (model) {
    return model
  }
  return summary.persisted ? 'Saved with the story' : 'Created for this run'
}

export function shouldShowArticleEmbeddingSummary(
  summary: ProcessedItemArticleEmbedding | undefined,
): boolean {
  return Boolean(summary && summary.present)
}
