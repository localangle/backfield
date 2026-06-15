export const ARTICLE_METADATA_DEFAULT_PRESET = 'subject' as const

export const ARTICLE_METADATA_PRESET_OPTIONS = [
  { id: 'subject', label: 'Subject' },
  { id: 'topic', label: 'Topic' },
  { id: 'temporal_orientation', label: 'Timeframe' },
  { id: 'format', label: 'Format' },
  { id: 'geographic_scope', label: 'Scope' },
  { id: 'information_needs', label: 'Critical information need' },
  { id: 'user_need', label: 'User need' },
  { id: 'custom', label: 'Custom' },
] as const

export type ArticleMetadataPresetId = (typeof ARTICLE_METADATA_PRESET_OPTIONS)[number]['id']

export function normalizeArticleMetadataPresetId(raw: unknown): ArticleMetadataPresetId {
  const value =
    typeof raw === 'string'
      ? raw.trim().toLowerCase().replace(/-/g, '_')
      : ARTICLE_METADATA_DEFAULT_PRESET
  const match = ARTICLE_METADATA_PRESET_OPTIONS.find((option) => option.id === value)
  return match?.id ?? ARTICLE_METADATA_DEFAULT_PRESET
}

/** User-facing preset label for graph nodes and summaries. */
export function getArticleMetadataPresetDisplayLabel(params: {
  prompt_preset?: unknown
  meta_type?: unknown
}): string {
  const presetId = normalizeArticleMetadataPresetId(params.prompt_preset)
  if (presetId === 'custom') {
    const metaType = typeof params.meta_type === 'string' ? params.meta_type.trim() : ''
    if (metaType) {
      return metaType.replace(/_/g, ' ')
    }
    return ARTICLE_METADATA_PRESET_OPTIONS.find((option) => option.id === 'custom')?.label ?? 'Custom'
  }
  return (
    ARTICLE_METADATA_PRESET_OPTIONS.find((option) => option.id === presetId)?.label ??
    presetId.replace(/_/g, ' ')
  )
}
