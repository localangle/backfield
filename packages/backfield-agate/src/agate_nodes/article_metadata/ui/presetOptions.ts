export const ARTICLE_METADATA_PRESET_OPTIONS = [
  { id: 'topic', label: 'Topic' },
  { id: 'subject', label: 'Subject' },
  { id: 'temporal_orientation', label: 'Timeframe' },
  { id: 'format', label: 'Format' },
  { id: 'geographic_scope', label: 'Scope' },
  { id: 'information_needs', label: 'Critical information need' },
  { id: 'user_need', label: 'User need' },
  { id: 'jobs_to_be_done', label: 'Jobs to be done' },
  { id: 'custom', label: 'Custom' },
] as const

export type ArticleMetadataPresetId = (typeof ARTICLE_METADATA_PRESET_OPTIONS)[number]['id']
