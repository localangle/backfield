import { describe, expect, it } from "vitest"
import {
  canStartCandidateAiReview,
  candidateProjectFilterState,
  candidateProjectOptions,
} from "@/lib/stylebook-api/stylebookCandidates"

describe("candidate project filter", () => {
  it("defaults to all accessible projects", () => {
    expect(
      candidateProjectFilterState("", [
        { project_id: 1, project_slug: "news", project_name: "News", count: 2 },
        { project_id: 2, project_slug: "sports", project_name: "Sports", count: 1 },
      ]),
    ).toEqual({ value: "all", visible: true })
  })

  it("hides the filter when only one project contributes", () => {
    expect(
      candidateProjectFilterState("", [
        { project_id: 1, project_slug: "news", project_name: "News", count: 2 },
        { project_id: 2, project_slug: "sports", project_name: "Sports", count: 0 },
      ]),
    ).toEqual({ value: "all", visible: false })
  })

  it("keeps a selected zero-result project filter visible", () => {
    const projects = [
      { project_id: 1, project_slug: "news", project_name: "News", count: 2 },
      { project_id: 2, project_slug: "sports", project_name: "Sports", count: 0 },
    ]
    expect(candidateProjectFilterState("sports", projects)).toEqual({
      value: "sports",
      visible: true,
    })
    expect(
      candidateProjectOptions("sports", projects).map((project) => project.project_slug),
    ).toEqual(["news", "sports"])
  })

  it("requires a selected project for AI review", () => {
    expect(canStartCandidateAiReview("")).toBe(false)
    expect(canStartCandidateAiReview("news")).toBe(true)
  })
})
