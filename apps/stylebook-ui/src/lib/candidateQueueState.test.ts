import { describe, expect, it } from "vitest"
import {
  CandidateQueueRequestGate,
  updateCandidateProjectFilter,
  validCandidateTypeFilter,
} from "@/lib/candidateQueueState"

describe("CandidateQueueRequestGate", () => {
  it("rejects responses from an older queue scope", () => {
    const gate = new CandidateQueueRequestGate()
    gate.setScope("default|news|open|page-1")
    const oldRequest = gate.begin("default|news|open|page-1")
    expect(oldRequest).not.toBeNull()

    gate.setScope("default|sports|open|page-1")

    expect(gate.isCurrent(oldRequest!)).toBe(false)
    expect(gate.begin("default|news|open|page-1")).toBeNull()
  })

  it("keeps only the newest request in one scope current", () => {
    const gate = new CandidateQueueRequestGate()
    gate.setScope("default|news|open|page-1")
    const first = gate.begin("default|news|open|page-1")
    const second = gate.begin("default|news|open|page-1")

    expect(gate.isCurrent(first!)).toBe(false)
    expect(gate.isCurrent(second!)).toBe(true)
  })
})

describe("candidate project navigation", () => {
  it("preserves workflow scope when setting and clearing evidence filters", () => {
    const initial = new URLSearchParams("project_scope=workflow&project=news&tab=review")

    const selected = updateCandidateProjectFilter(initial, "sports")
    expect(selected.toString()).toBe("project_scope=workflow&project=sports&tab=review")

    const all = updateCandidateProjectFilter(selected, "all")
    expect(all.toString()).toBe("project_scope=workflow&tab=review")
  })
})

describe("candidate type filters", () => {
  it("resets a selection that is unavailable in the new scope", () => {
    expect(validCandidateTypeFilter("county", ["city", "county"])).toBe("county")
    expect(validCandidateTypeFilter("county", ["city"])).toBe("all")
    expect(validCandidateTypeFilter("all", [])).toBe("all")
  })
})
