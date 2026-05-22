/** Destructive confirmation copy for re-runs that replace saved review edits. */

export const RERUN_WARNING_TITLE = 'Rerun item?'

/** Run detail **Run Again** (new full run that replaces persisted review state). */
export const RUN_AGAIN_WARNING_TITLE = 'Rerun all items?'
export const RUN_AGAIN_WARNING_BODY =
  'Re-running will replace all manual edits that have been made to all selected items.'

export const rerunWarningTitle = (itemCount = 1): string =>
  itemCount === 1 ? RERUN_WARNING_TITLE : 'Rerun items?'

export const rerunWarningBody = (itemCount = 1): string => {
  const itemPhrase =
    itemCount === 1 ? 'this item' : `these ${itemCount} items`
  return `Re-running will replace all manual edits that have been made to ${itemPhrase}.`
}
