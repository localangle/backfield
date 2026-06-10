export const ARTICLE_METADATA_PRESET_OPTIONS = [
  { id: 'topic', label: 'Topic' },
  { id: 'temporal_orientation', label: 'Temporal orientation' },
  { id: 'geographic_scope', label: 'Geographic scope' },
  { id: 'information_needs', label: 'Information needs' },
  { id: 'jobs_to_be_done', label: 'Jobs to be done' },
  { id: 'custom', label: 'Custom' },
] as const

export type ArticleMetadataPresetId = (typeof ARTICLE_METADATA_PRESET_OPTIONS)[number]['id']
