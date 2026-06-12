import type { ProcessedItem } from '@/lib/api'
import { customRecordsOverlayHasContent } from '@/lib/review/entities/custom/customRecordsOverlay'

export type EditorReviewSection =
  | 'places'
  | 'people'
  | 'organizations'
  | 'story'
  | 'meta'
  | 'custom'

export const EDITOR_REVIEW_BANNER_COPY: Record<EditorReviewSection, string> = {
  places: 'Place data for this article has been corrected or enhanced by an editor.',
  people: 'People data for this article has been corrected or enhanced by an editor.',
  organizations:
    'Organization data for this article has been corrected or enhanced by an editor.',
  story: 'Story details for this article have been corrected or enhanced by an editor.',
  meta: 'Metadata tags for this article have been corrected or enhanced by an editor.',
  custom: 'Custom records for this article have been corrected or enhanced by an editor.',
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

function anchorEntityOverlayHasContent(root: unknown): boolean {
  if (!isPlainObject(root)) return false
  const byAnchor = root.by_anchor
  if (isPlainObject(byAnchor) && Object.keys(byAnchor).length > 0) return true
  if (Array.isArray(root.user_added) && root.user_added.length > 0) return true
  if (Array.isArray(root.removed_anchors) && root.removed_anchors.length > 0) return true
  return false
}

function articleMetaOverlayHasContent(overlay: Record<string, unknown> | null | undefined): boolean {
  if (!isPlainObject(overlay)) return false
  const root = overlay.article_meta
  if (!isPlainObject(root)) return false
  const byId = root.by_id
  if (isPlainObject(byId) && Object.keys(byId).length > 0) return true
  if (Array.isArray(root.user_added) && root.user_added.length > 0) return true
  if (Array.isArray(root.removed_ids) && root.removed_ids.length > 0) return true
  if (Array.isArray(root.removed_meta_types) && root.removed_meta_types.length > 0) return true
  return false
}

function storyOverlayHasContent(overlay: Record<string, unknown> | null | undefined): boolean {
  if (!isPlainObject(overlay)) return false
  const article = overlay.article
  return isPlainObject(article) && Object.keys(article).length > 0
}

/** True when saved review overlay (or stale orphan patches) indicate editor changes for a section. */
export function processedItemSectionEditorTouched(
  item: ProcessedItem,
  section: EditorReviewSection,
): boolean {
  const overlay = item.overlay
  switch (section) {
    case 'places':
      return (
        (item.stale_overlay_entries?.length ?? 0) > 0 ||
        anchorEntityOverlayHasContent(overlay?.locations)
      )
    case 'people':
      return (
        (item.stale_people_overlay_entries?.length ?? 0) > 0 ||
        anchorEntityOverlayHasContent(overlay?.people)
      )
    case 'organizations':
      return (
        (item.stale_organizations_overlay_entries?.length ?? 0) > 0 ||
        anchorEntityOverlayHasContent(overlay?.organizations)
      )
    case 'story':
      return storyOverlayHasContent(overlay)
    case 'meta':
      if (articleMetaOverlayHasContent(overlay)) return true
      return (item.article_meta ?? []).some((row) => row.source === 'review')
    case 'custom':
      return customRecordsOverlayHasContent(overlay)
    default:
      return false
  }
}
