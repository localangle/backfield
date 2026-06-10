export type ProcessedItemArticleMetaRow = {
  id: number
  meta_type: string
  category: string
  rationale: string
  confidence: number
  prompt_preset?: string | null
  updated_at?: string | null
  source: 'model' | 'review'
}

const META_TYPE_LABELS: Record<string, string> = {
  topic: 'Topic',
  subject: 'Subject',
  temporal_orientation: 'Timeframe',
  format: 'Format',
  geographic_scope: 'Scope',
  information_needs: 'Critical information need',
  user_need: 'User need',
  jobs_to_be_done: 'Jobs to be done',
  custom: 'Custom',
}

export function articleMetaTypeLabel(metaType: string): string {
  const key = metaType.trim().toLowerCase()
  if (META_TYPE_LABELS[key]) return META_TYPE_LABELS[key]
  return key.replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase())
}

export function normalizeProcessedItemArticleMetaRows(
  raw: unknown,
): ProcessedItemArticleMetaRow[] {
  if (!Array.isArray(raw)) return []
  const rows: ProcessedItemArticleMetaRow[] = []
  for (const entry of raw) {
    if (!entry || typeof entry !== 'object') continue
    const row = entry as Record<string, unknown>
    const id = row.id
    const metaType = row.meta_type
    const category = row.category
    const rationale = row.rationale
    const confidence = row.confidence
    if (
      typeof id !== 'number' ||
      typeof metaType !== 'string' ||
      typeof category !== 'string' ||
      typeof rationale !== 'string' ||
      typeof confidence !== 'number'
    ) {
      continue
    }
    rows.push({
      id,
      meta_type: metaType,
      category,
      rationale,
      confidence,
      prompt_preset: typeof row.prompt_preset === 'string' ? row.prompt_preset : null,
      updated_at: typeof row.updated_at === 'string' ? row.updated_at : null,
      source: row.source === 'review' ? 'review' : 'model',
    })
  }
  return rows
}
