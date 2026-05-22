/** Label for the Source column while batch items are still being created from S3. */
export const PREPARING_ITEMS_SOURCE_LABEL = 'Preparing items ...'

/** Run detail placeholder: server counts are zero but the UI shows a synthetic row. */
export function isRunPreparingItems(run: {
  total_items: number
  items?: readonly unknown[] | null
}): boolean {
  return run.total_items === 0 && (run.items?.length ?? 0) > 0
}
