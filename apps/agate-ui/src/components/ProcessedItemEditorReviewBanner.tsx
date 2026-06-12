import { Alert, AlertDescription } from '@/components/ui/alert'
import type { ProcessedItem } from '@/lib/api'
import {
  EDITOR_REVIEW_BANNER_COPY,
  processedItemSectionEditorTouched,
  type EditorReviewSection,
} from '@/lib/review/overlay/editorReviewBanner'

export type ProcessedItemEditorReviewBannerProps = {
  item: ProcessedItem
  section: EditorReviewSection
}

/** Amber notice when a review section carries saved editor corrections. */
export function ProcessedItemEditorReviewBanner({
  item,
  section,
}: ProcessedItemEditorReviewBannerProps) {
  if (!processedItemSectionEditorTouched(item, section)) {
    return null
  }

  return (
    <Alert
      variant="default"
      className="border-amber-200 bg-amber-50 text-amber-950 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-50"
    >
      <AlertDescription>{EDITOR_REVIEW_BANNER_COPY[section]}</AlertDescription>
    </Alert>
  )
}
