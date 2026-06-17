import { createElement } from "react"
import type { CandidateQueueTableLayout } from "@/lib/entityConfigs/candidateQueueTypes"

export const CANDIDATE_QUEUE_ACTIONS_WIDTH = "11rem"

/** Primary + config columns + actions. */
export function candidateQueueColumnCount(dataColumnCount: number): number {
  return dataColumnCount + 2
}

export function resolveCandidateQueueColgroup(
  columnCount: number,
  layout?: CandidateQueueTableLayout,
): Array<{ width: string }> {
  if (layout?.colgroup && layout.colgroup.length === columnCount) {
    return layout.colgroup
  }

  const actions = layout?.actionsColumnWidth ?? CANDIDATE_QUEUE_ACTIONS_WIDTH
  switch (columnCount) {
    case 3:
      return [{ width: "52%" }, { width: "18%" }, { width: actions }]
    case 4:
      return [{ width: "40%" }, { width: "14%" }, { width: "20%" }, { width: actions }]
    case 5:
      return [
        { width: "34%" },
        { width: "12%" },
        { width: "14%" },
        { width: "15%" },
        { width: actions },
      ]
    case 6:
      return [
        { width: "28%" },
        { width: "12%" },
        { width: "22%" },
        { width: "10%" },
        { width: "10%" },
        { width: actions },
      ]
    default: {
      const dataColumns = Math.max(columnCount - 1, 1)
      const share = `${Math.floor(100 / dataColumns)}%`
      return [
        ...Array.from({ length: dataColumns }, () => ({ width: share })),
        { width: actions },
      ]
    }
  }
}

export const candidateQueueDataCellClass = "min-w-0 align-top overflow-hidden"

export function truncateCellText(value: string, title?: string) {
  return createElement(
    "span",
    {
      className: "block truncate",
      title: title ?? (value !== "—" ? value : undefined),
    },
    value,
  )
}
