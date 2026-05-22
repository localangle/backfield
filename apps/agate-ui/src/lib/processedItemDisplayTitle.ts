import type { ArticleContext } from '@/lib/api'

const HEADLINE_KEYS = ['headline', 'title', 'input_headline'] as const

/** Worker substrate default when consolidated JSON has no headline. */
const GENERIC_HEADLINE_PLACEHOLDERS = new Set(['article'])

function isGenericHeadline(value: string): boolean {
  return GENERIC_HEADLINE_PLACEHOLDERS.has(value.trim().toLowerCase())
}

function pickHeadline(obj: Record<string, unknown> | null | undefined): string | null {
  if (!obj) return null
  for (const key of HEADLINE_KEYS) {
    const v = obj[key]
    if (typeof v === 'string' && v.trim()) {
      const trimmed = v.trim()
      if (!isGenericHeadline(trimmed)) return trimmed
    }
  }
  return null
}

/** Page title for a processed item — headline when known, otherwise a short item label. */
export function processedItemDisplayTitle(item: {
  id: number
  article_context?: ArticleContext | null
  input?: Record<string, unknown>
  output?: Record<string, unknown> | null
  overlay?: Record<string, unknown> | null
}): string {
  const overlayArticle = item.overlay?.article
  if (overlayArticle && typeof overlayArticle === 'object' && !Array.isArray(overlayArticle)) {
    const fromOverlay = pickHeadline(overlayArticle as Record<string, unknown>)
    if (fromOverlay) return fromOverlay
  }

  const fromInput = pickHeadline(item.input)
  if (fromInput) return fromInput

  const fromArticle = item.article_context?.headline?.trim()
  if (fromArticle && !isGenericHeadline(fromArticle)) return fromArticle

  const fromOutput = pickHeadline(item.output ?? undefined)
  if (fromOutput) return fromOutput

  return `Processed Item #${item.id}`
}
