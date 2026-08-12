import { describe, expect, it } from "vitest"
import {
  defaultWorkflowProjectSlug,
  projectOwnsStylebook,
  projectSlugsOwningStylebook,
} from "@/lib/workflowProjectScope"

const projects = [
  { slug: "general" },
  { slug: "demo" },
  { slug: "workbooks" },
]

const workspaces = [
  {
    stylebook_id: 3,
    projects: [{ slug: "general" }],
  },
  {
    stylebook_id: 5,
    projects: [{ slug: "demo" }, { slug: "workbooks" }],
  },
]

describe("workflowProjectScope", () => {
  it("lists projects that own a stylebook", () => {
    expect(projectSlugsOwningStylebook(workspaces, 5)).toEqual(["demo", "workbooks"])
    expect(projectOwnsStylebook("general", 5, workspaces)).toBe(false)
    expect(projectOwnsStylebook("demo", 5, workspaces)).toBe(true)
  })

  it("prefers an owning project over bare general for a catalog", () => {
    expect(
      defaultWorkflowProjectSlug(projects, {
        stylebookId: 5,
        workspaces,
      }),
    ).toBe("demo")
  })

  it("still prefers general when general owns the catalog", () => {
    expect(
      defaultWorkflowProjectSlug(projects, {
        stylebookId: 3,
        workspaces,
      }),
    ).toBe("general")
  })

  it("falls back to general when ownership is unknown", () => {
    expect(defaultWorkflowProjectSlug(projects)).toBe("general")
    expect(
      defaultWorkflowProjectSlug(projects, { stylebookId: 99, workspaces }),
    ).toBe("general")
  })
})
