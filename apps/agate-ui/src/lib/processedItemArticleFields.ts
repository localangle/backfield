import type { ProcessedItem } from '@/lib/api'
import { normalizeOverlay } from '@/lib/processedItemVerificationOverlay'

export const ARTICLE_FIELD_KEYS = [
  'publication',
  'url',
  'headline',
  'author',
  'pub_date',
] as const

export type ArticleFieldKey = (typeof ARTICLE_FIELD_KEYS)[number]

export const ARTICLE_FIELD_LABELS: Record<ArticleFieldKey, string> = {
  publication: 'Source',
  url: 'URL',
  headline: 'Headline',
  author: 'Author',
  pub_date: 'Publication date',
}

export type ArticleFields = Record<ArticleFieldKey, string>

export function emptyArticleFields(): ArticleFields {
  return {
    publication: '',
    url: '',
    headline: '',
    author: '',
    pub_date: '',
  }
}

function pickString(obj: Record<string, unknown> | undefined, keys: readonly string[]): string {
  if (!obj) return ''
  for (const key of keys) {
    const v = obj[key]
    if (typeof v === 'string' && v.trim()) return v.trim()
  }
  return ''
}

const INPUT_KEYS: Record<ArticleFieldKey, readonly string[]> = {
  publication: ['publication', 'source'],
  url: ['url'],
  headline: ['headline', 'title', 'input_headline'],
  author: ['author'],
  pub_date: ['pub_date', 'publication_date'],
}

/** Collect article-shaped dicts from per-node run output (``json_output.consolidated``, hoisted DBOutput, etc.). */
export function articleFieldSourcesFromNodeOutputs(
  nodeOutputs: Record<string, unknown> | null | undefined,
): Record<string, unknown>[] {
  if (!nodeOutputs || typeof nodeOutputs !== 'object') return []
  const sources: Record<string, unknown>[] = []
  if (ARTICLE_FIELD_KEYS.some((key) => key in nodeOutputs)) {
    sources.push(nodeOutputs)
  }
  for (const payload of Object.values(nodeOutputs)) {
    if (!payload || typeof payload !== 'object' || Array.isArray(payload)) continue
    const block = payload as Record<string, unknown>
    const consolidated = block.consolidated
    if (consolidated && typeof consolidated === 'object' && !Array.isArray(consolidated)) {
      sources.push(consolidated as Record<string, unknown>)
    }
    sources.push(block)
  }
  return sources
}

/** Resolved article metadata for the item info form (overlay → reviewed/output nodes → input → article context). */
export function readArticleFieldsFromProcessedItem(item: ProcessedItem): ArticleFields {
  const input = item.input ?? {}
  const overlayRaw = item.overlay?.article
  const overlayArticle =
    overlayRaw && typeof overlayRaw === 'object' && !Array.isArray(overlayRaw)
      ? (overlayRaw as Record<string, unknown>)
      : undefined

  const outputSources = articleFieldSourcesFromNodeOutputs(item.output)
  const reviewedSources = articleFieldSourcesFromNodeOutputs(item.reviewed_output ?? undefined)

  const ctxHeadline =
    typeof item.article_context?.headline === 'string' ? item.article_context.headline.trim() : ''

  const out: ArticleFields = emptyArticleFields()
  for (const key of ARTICLE_FIELD_KEYS) {
    const keys = INPUT_KEYS[key]
    let value = pickString(overlayArticle, keys)
    if (!value) {
      for (const source of reviewedSources) {
        value = pickString(source, keys)
        if (value) break
      }
    }
    if (!value) {
      for (const source of outputSources) {
        value = pickString(source, keys)
        if (value) break
      }
    }
    if (!value) {
      value = pickString(input, keys)
    }
    out[key] =
      value || (key === 'headline' && ctxHeadline ? ctxHeadline : '')
  }
  return out
}

export function articleFieldsEqual(a: ArticleFields, b: ArticleFields): boolean {
  return ARTICLE_FIELD_KEYS.every((k) => a[k] === b[k])
}

export function applyArticleFieldsToOverlay(
  overlay: Record<string, unknown> | null | undefined,
  fields: ArticleFields,
): Record<string, unknown> {
  const next = normalizeOverlay(overlay)
  next.article = { ...fields }
  return next
}
