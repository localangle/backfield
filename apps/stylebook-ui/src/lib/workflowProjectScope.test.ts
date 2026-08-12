import { describe, expect, it } from "vitest"
import {
  defaultWorkflowProjectSlug,
  owningProjectSlugsForStylebook,
  projectOwnsStylebook,
  replacementWorkflowProjectSlug,
} from "@/lib/workflowProjectScope"

const projects = [
  { slug: "general", stylebook_id: 3, stylebook_slug: "cpm-stylebook" },
  { slug: "demo", stylebook_id: 5, stylebook_slug: "demo-stylebook" },
  { slug: "workbooks", stylebook_id: 5, stylebook_slug: "demo-stylebook" },
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
  it("lists projects that own a stylebook from Agate project fields", () => {
    expect(owningProjectSlugsForStylebook(5, projects, [])).toEqual([
      "demo",
      "workbooks",
    ])
    expect(projectOwnsStylebook("general", 5, projects, workspaces)).toBe(false)
    expect(projectOwnsStylebook("demo", 5, projects, workspaces)).toBe(true)
  })

  it("falls back to workspace ownership when projects omit stylebook_id", () => {
    const bare = [{ slug: "general" }, { slug: "demo" }, { slug: "workbooks" }]
    expect(owningProjectSlugsForStylebook(5, bare, workspaces)).toEqual([
      "demo",
      "workbooks",
    ])
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

  it("does not rewrite mismatched scope when no owner exists", () => {
    expect(
      replacementWorkflowProjectSlug("general", 99, projects, workspaces),
    ).toBeNull()
  })

  it("rewrites mismatched scope to an owning project", () => {
    expect(
      replacementWorkflowProjectSlug("general", 5, projects, workspaces),
    ).toBe("demo")
    expect(
      replacementWorkflowProjectSlug("demo", 5, projects, workspaces),
    ).toBeNull()
  })
})
