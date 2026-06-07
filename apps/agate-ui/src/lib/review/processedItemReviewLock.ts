import type { ProcessedItem } from '@/lib/api'

/** True while a rerun is in flight or the item is pending/running in the worker. */
export function isProcessedItemReviewLocked(
  item: Pick<ProcessedItem, 'status'>,
  rerunBusy: boolean,
): boolean {
  return rerunBusy || item.status === 'pending' || item.status === 'running'
}
