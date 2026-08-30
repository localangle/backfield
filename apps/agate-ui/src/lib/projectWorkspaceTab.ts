/** Project detail workspace tabs (``ProjectDetailPage``). */

export const PROJECT_WORKSPACE_TABS = [
  'flows',
  'runs',
  'articles',
  'models',
  'integrations',
  'keys',
] as const

export type ProjectWorkspaceTab = (typeof PROJECT_WORKSPACE_TABS)[number]

export function defaultProjectWorkspaceTab(): ProjectWorkspaceTab {
  return 'flows'
}

export function isProjectWorkspaceTab(value: string): value is ProjectWorkspaceTab {
  return (PROJECT_WORKSPACE_TABS as readonly string[]).includes(value)
}

export function parseProjectWorkspaceTab(
  raw: string | null | undefined,
): ProjectWorkspaceTab {
  if (raw && isProjectWorkspaceTab(raw)) {
    return raw
  }
  return defaultProjectWorkspaceTab()
}

/** Build search string for a workspace tab permalink (includes leading ``?``). */
export function projectWorkspaceTabSearch(tab: ProjectWorkspaceTab): string {
  const params = new URLSearchParams()
  params.set('tab', tab)
  return `?${params.toString()}`
}
