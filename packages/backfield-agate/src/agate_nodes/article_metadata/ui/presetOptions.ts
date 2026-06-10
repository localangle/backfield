export const ARTICLE_METADATA_DEFAULT_PRESET = 'subject' as const

export const ARTICLE_METADATA_PRESET_OPTIONS = [
  { id: 'subject', label: 'Subject' },
  { id: 'temporal_orientation', label: 'Timeframe' },
  { id: 'format', label: 'Format' },
  { id: 'geographic_scope', label: 'Scope' },
  { id: 'information_needs', label: 'Critical information need' },
  { id: 'user_need', label: 'User need' },
  { id: 'custom', label: 'Custom' },
] as const

export type ArticleMetadataPresetId = (typeof ARTICLE_METADATA_PRESET_OPTIONS)[number]['id']
