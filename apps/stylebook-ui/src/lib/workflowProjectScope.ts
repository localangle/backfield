/** Pick workflow ``project_scope`` that matches the path Stylebook catalog. */

export type WorkflowProjectRef = {
  slug: string
  stylebook_id?: number | null
  stylebook_slug?: string | null
}

export type WorkflowWorkspaceRef = {
  stylebook_id?: number | null
  projects: { slug: string }[]
}

function uniqueSlugs(slugs: string[]): string[] {
  const out: string[] = []
  const seen = new Set<string>()
  for (const slug of slugs) {
    if (seen.has(slug)) continue
    seen.add(slug)
    out.push(slug)
  }
  return out
}

/** Prefer Agate project ``stylebook_id``; fall back to workspace assignment. */
export function owningProjectSlugsForStylebook(
  stylebookId: number,
  projects: WorkflowProjectRef[],
  workspaces: WorkflowWorkspaceRef[] = [],
): string[] {
  const fromProjects = projects
    .filter((project) => project.stylebook_id === stylebookId)
    .map((project) => project.slug)
  if (fromProjects.length > 0) {
    return uniqueSlugs(fromProjects)
  }

  const visible = new Set(projects.map((project) => project.slug))
  const fromWorkspaces: string[] = []
  for (const ws of workspaces) {
    if (ws.stylebook_id !== stylebookId) continue
    for (const project of ws.projects) {
      if (!visible.has(project.slug)) continue
      fromWorkspaces.push(project.slug)
    }
  }
  return uniqueSlugs(fromWorkspaces)
}

export function projectOwnsStylebook(
  projectSlug: string,
  stylebookId: number,
  projects: WorkflowProjectRef[],
  workspaces: WorkflowWorkspaceRef[] = [],
): boolean {
  return owningProjectSlugsForStylebook(stylebookId, projects, workspaces).includes(
    projectSlug,
  )
}

function preferGeneralThenFirst(slugs: string[]): string {
  return slugs.find((slug) => slug === "general") ?? slugs[0] ?? ""
}

/**
 * Default Agate project when the URL omits ``project_scope``.
 * Prefers an owner of ``stylebookId``, else ``general`` / first visible project.
 */
export function defaultWorkflowProjectSlug(
  projects: WorkflowProjectRef[],
  options?: {
    stylebookId?: number | null
    workspaces?: WorkflowWorkspaceRef[]
  },
): string {
  const stylebookId = options?.stylebookId
  const workspaces = options?.workspaces ?? []
  if (stylebookId != null) {
    const owners = owningProjectSlugsForStylebook(stylebookId, projects, workspaces)
    const owning = preferGeneralThenFirst(owners)
    if (owning) return owning
  }
  return preferGeneralThenFirst(projects.map((project) => project.slug))
}

/**
 * When ``project_scope`` does not own the path catalog, return a better owning
 * slug. Returns null when scope is already fine or no owner is known (do not
 * rewrite the URL — rewriting to the same mismatched default caused a loop).
 */
export function replacementWorkflowProjectSlug(
  currentProjectSlug: string,
  stylebookId: number,
  projects: WorkflowProjectRef[],
  workspaces: WorkflowWorkspaceRef[] = [],
): string | null {
  const owners = owningProjectSlugsForStylebook(stylebookId, projects, workspaces)
  if (owners.length === 0) return null
  if (owners.includes(currentProjectSlug)) return null
  const next = preferGeneralThenFirst(owners)
  if (!next || next === currentProjectSlug) return null
  return next
}
