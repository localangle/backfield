/** Processed item detail page tabs (``ProcessedItemDetail``). */
export const PROCESSED_ITEM_DETAIL_TABS = [
  'info',
  'places',
  'people',
  'organizations',
  'images',
  'meta',
  'custom',
  'json',
] as const

export type ProcessedItemDetailTab = (typeof PROCESSED_ITEM_DETAIL_TABS)[number]

export function defaultProcessedItemDetailTab(_synthetic: boolean): ProcessedItemDetailTab {
  return 'info'
}

export function isProcessedItemDetailTab(value: string): value is ProcessedItemDetailTab {
  return (PROCESSED_ITEM_DETAIL_TABS as readonly string[]).includes(value)
}

/** Read ``tab`` from ``?tab=`` first, then ``#`` fragment (legacy / share links). */
export function readProcessedItemTabFromLocation(searchParams: URLSearchParams): string | null {
  const fromQuery = searchParams.get('tab')?.trim()
  if (fromQuery) return fromQuery
  if (typeof window === 'undefined') return null
  const hash = window.location.hash.replace(/^#/, '').trim()
  return hash || null
}

export function parseProcessedItemDetailTab(
  raw: string | null | undefined,
  options: { synthetic: boolean },
): ProcessedItemDetailTab {
  if (raw && isProcessedItemDetailTab(raw)) {
    return raw
  }
  return defaultProcessedItemDetailTab(options.synthetic)
}

/** Build search string for a tab permalink (includes leading ``?`` when non-empty). */
export function processedItemDetailTabSearch(tab: ProcessedItemDetailTab): string {
  const params = new URLSearchParams()
  params.set('tab', tab)
  return `?${params.toString()}`
}
