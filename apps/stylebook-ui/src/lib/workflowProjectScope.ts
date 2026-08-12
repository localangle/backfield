/** Pick workflow ``project_scope`` that matches the path Stylebook catalog. */

export type WorkflowProjectRef = { slug: string }

export type WorkflowWorkspaceRef = {
  stylebook_id?: number | null
  projects: WorkflowProjectRef[]
}

/** Project slugs under workspaces assigned to ``stylebookId``. */
export function projectSlugsOwningStylebook(
  workspaces: WorkflowWorkspaceRef[],
  stylebookId: number,
): string[] {
  const slugs: string[] = []
  const seen = new Set<string>()
  for (const ws of workspaces) {
    if (ws.stylebook_id !== stylebookId) continue
    for (const project of ws.projects) {
      if (seen.has(project.slug)) continue
      seen.add(project.slug)
      slugs.push(project.slug)
    }
  }
  return slugs
}

export function projectOwnsStylebook(
  projectSlug: string,
  stylebookId: number,
  workspaces: WorkflowWorkspaceRef[],
): boolean {
  return projectSlugsOwningStylebook(workspaces, stylebookId).includes(projectSlug)
}

/**
 * Default Agate project for catalog workflow when the URL omits scope, or when
 * the current scope does not own the path Stylebook.
 *
 * Prefers ``general`` among projects that own the catalog; otherwise the first
 * owning visible project; then falls back to ``general`` / first project overall.
 */
export function defaultWorkflowProjectSlug(
  projects: WorkflowProjectRef[],
  options?: {
    stylebookId?: number | null
    workspaces?: WorkflowWorkspaceRef[]
  },
): string {
  const visible = new Set(projects.map((project) => project.slug))
  const stylebookId = options?.stylebookId
  const workspaces = options?.workspaces ?? []
  if (stylebookId != null) {
    const owners = projectSlugsOwningStylebook(workspaces, stylebookId).filter((slug) =>
      visible.has(slug),
    )
    const preferredOwner = owners.find((slug) => slug === "general")
    if (preferredOwner) return preferredOwner
    if (owners[0]) return owners[0]
  }
  const preferred = projects.find((project) => project.slug === "general")
  return preferred?.slug ?? projects[0]?.slug ?? ""
}
