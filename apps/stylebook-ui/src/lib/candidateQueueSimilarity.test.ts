import { describe, expect, it } from "vitest"
import {
  candidateQueueNameKey,
  duplicateCreateNewClusters,
  duplicateCreateNewSummary,
  normalizeLabelForCompare,
} from "@/lib/candidateQueueSimilarity"

describe("candidateQueueSimilarity", () => {
  it("normalizes labels for comparison", () => {
    expect(normalizeLabelForCompare("  Ronald  Acuña ")).toBe("ronald acuna")
  })

  it("groups duplicate create-new suggestions by normalized name", () => {
    const rows = [
      {
        id: 1,
        canonical_suggestion: { suggested_action: "materialize_new" },
        name: "Ronald Acuña",
      },
      {
        id: 2,
        canonical_suggestion: { suggested_action: "materialize_new" },
        name: "Ronald Acuña",
      },
      {
        id: 3,
        canonical_suggestion: { suggested_action: "link_existing" },
        name: "Ronald Acuña",
      },
      {
        id: 4,
        canonical_suggestion: { suggested_action: "materialize_new" },
        name: "Mike Trout",
      },
    ]

    const clusters = duplicateCreateNewClusters(rows, (row) => row.name)
    expect(clusters).toEqual([
      { nameKey: candidateQueueNameKey("Ronald Acuña"), displayName: "Ronald Acuña", count: 2 },
    ])

    const summary = duplicateCreateNewSummary(rows, (row) => row.name)
    expect(summary.duplicateNameCount).toBe(1)
    expect(summary.totalExtraRows).toBe(1)
  })
})
