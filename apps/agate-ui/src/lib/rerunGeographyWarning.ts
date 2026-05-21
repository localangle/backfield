/** Destructive confirmation copy for re-runs that replace saved story geography. */

export const RERUN_GEOGRAPHY_WARNING_TITLE = 'Replace saved places?'

export const rerunGeographyWarningBody = (itemCount = 1): string => {
  const storyPhrase =
    itemCount === 1
      ? 'this story'
      : `these ${itemCount} stories`
  return (
    `Re-running will replace all saved places and review edits for ${storyPhrase} ` +
    'with new results from the workflow. Places linked on other stories are not removed—only ' +
    'this story’s links and mentions are cleared before the new run is saved.'
  )
}
