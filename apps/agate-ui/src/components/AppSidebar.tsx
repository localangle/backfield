import { useCallback, useEffect, useMemo, useState } from 'react'
import { matchPath, NavLink, useLocation } from 'react-router-dom'
import {
  ChevronDown,
  ChevronRight,
  HelpCircle,
  Settings,
} from 'lucide-react'
import { AgateProductMark, ShellSidebar, StylebookProductMark } from '@backfield/ui'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { listProjects, type Project } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { listMyWorkspaces, type WorkspaceWithProjects } from '@/lib/core-api'
import { hasWorkspaceAccess } from '@/lib/workspace-access'
import { helpHref, stylebookShellHref } from '@/lib/platformUrls'
import {
  listStylebookCatalogs,
  type StylebookCatalogRow,
} from '@/lib/stylebook-org-api'

const STORAGE_EXPANDED = 'agate-sidebar-expanded'
const STORAGE_WORKSPACES_EXPANDED = 'agate-sidebar-workspaces-expanded'

function readExpandedWorkspaceSlugs(): Set<string> {
  try {
    const raw = localStorage.getItem(STORAGE_WORKSPACES_EXPANDED)
    if (!raw) return new Set()
    const parsed = JSON.parse(raw) as unknown
    if (!Array.isArray(parsed)) return new Set()
    return new Set(parsed.filter((slug): slug is string => typeof slug === 'string'))
  } catch {
    return new Set()
  }
}

function pickProjectSlugForStylebookLinks(
  activeSlug: string | null,
  rows: WorkspaceWithProjects[],
): string | null {
  if (activeSlug) return activeSlug
  for (const ws of rows) {
    const first = ws.projects[0]
    if (first) return first.slug
  }
  return null
}

export default function AppSidebar() {
  const location = useLocation()
  const { organizationId, isOrgAdmin } = useAuth()
  const [workspaceRows, setWorkspaceRows] = useState<WorkspaceWithProjects[]>([])
  const [apiProjects, setApiProjects] = useState<Project[]>([])
  const [stylebooks, setStylebooks] = useState<StylebookCatalogRow[]>([])
  const [expandedWorkspaceSlugs, setExpandedWorkspaceSlugs] = useState<Set<string>>(
    readExpandedWorkspaceSlugs,
  )

  useEffect(() => {
    try {
      localStorage.setItem(
        STORAGE_WORKSPACES_EXPANDED,
        JSON.stringify([...expandedWorkspaceSlugs]),
      )
    } catch {
      /* ignore */
    }
  }, [expandedWorkspaceSlugs])

  const toggleWorkspaceExpanded = useCallback((workspaceSlug: string) => {
    setExpandedWorkspaceSlugs((prev) => {
      const next = new Set(prev)
      if (next.has(workspaceSlug)) next.delete(workspaceSlug)
      else next.add(workspaceSlug)
      return next
    })
  }, [])

  const loadWorkspaces = useCallback(async (): Promise<WorkspaceWithProjects[]> => {
    try {
      const rows = await listMyWorkspaces()
      setWorkspaceRows(rows)
      return rows
    } catch (e) {
      console.error(e)
      try {
        const fallback = await listProjects()
        const rows: WorkspaceWithProjects[] = [
          {
            id: 0,
            name: 'Projects',
            slug: '_flat',
            projects: fallback.map((p) => ({
              id: p.id,
              name: p.name,
              slug: p.slug,
            })),
          },
        ]
        setWorkspaceRows(rows)
        return rows
      } catch (e2) {
        console.error(e2)
        setWorkspaceRows([])
        return []
      }
    }
  }, [])

  const loadProjects = useCallback(async () => {
    try {
      const rows = await listProjects()
      setApiProjects(rows)
    } catch (e) {
      console.error(e)
      setApiProjects([])
    }
  }, [])

  useEffect(() => {
    void loadWorkspaces()
    void loadProjects()
  }, [loadWorkspaces, loadProjects, location.pathname])

  useEffect(() => {
    const onChanged = () => {
      void loadWorkspaces()
      void loadProjects()
    }
    window.addEventListener('agate:projects-changed', onChanged)
    window.addEventListener('agate:workspaces-changed', onChanged)
    return () => {
      window.removeEventListener('agate:projects-changed', onChanged)
      window.removeEventListener('agate:workspaces-changed', onChanged)
    }
  }, [loadWorkspaces, loadProjects])

  useEffect(() => {
    if (organizationId == null) {
      setStylebooks([])
      return
    }
    void listStylebookCatalogs(organizationId)
      .then(setStylebooks)
      .catch((err) => console.error('Failed to fetch stylebooks:', err))
  }, [organizationId])

  const hubLinkClass =
    'flex items-center gap-3 rounded-md px-2 py-2 text-sm font-medium transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring text-muted-foreground hover:text-foreground'

  const projectRouteMatch = matchPath(
    { path: '/project/:projectSlug', end: true },
    location.pathname,
  )
  const activeProjectSlug =
    projectRouteMatch?.params.projectSlug != null
      ? decodeURIComponent(projectRouteMatch.params.projectSlug)
      : null

  const workspaceRouteMatch = matchPath(
    { path: '/workspace/:workspaceSlug', end: true },
    location.pathname,
  )
  const activeWorkspaceSlug =
    workspaceRouteMatch?.params.workspaceSlug != null
      ? decodeURIComponent(workspaceRouteMatch.params.workspaceSlug)
      : null

  useEffect(() => {
    const slugsToExpand = new Set<string>()
    if (activeWorkspaceSlug) slugsToExpand.add(activeWorkspaceSlug)
    if (activeProjectSlug) {
      for (const ws of workspaceRows) {
        if (ws.projects.some((p) => p.slug === activeProjectSlug)) {
          slugsToExpand.add(ws.slug)
        }
      }
    }
    if (slugsToExpand.size === 0) return
    setExpandedWorkspaceSlugs((prev) => {
      let changed = false
      const next = new Set(prev)
      for (const slug of slugsToExpand) {
        if (!next.has(slug)) {
          next.add(slug)
          changed = true
        }
      }
      return changed ? next : prev
    })
  }, [activeWorkspaceSlug, activeProjectSlug, workspaceRows])

  const sortedStylebooks = useMemo(() => {
    return [...stylebooks].sort(
      (a, b) =>
        Number(b.is_default) - Number(a.is_default) ||
        a.name.localeCompare(b.name),
    )
  }, [stylebooks])

  const stylebookProjectSlug = pickProjectSlugForStylebookLinks(
    activeProjectSlug,
    workspaceRows,
  )

  const workspaceAccess = hasWorkspaceAccess(workspaceRows, isOrgAdmin)

  const headerTo =
    activeProjectSlug != null
      ? `/project/${encodeURIComponent(activeProjectSlug)}`
      : '/'

  const sectionTitleClass =
    'flex items-center gap-2 px-2 py-2 text-xs font-medium text-muted-foreground'

  const workspaceRowClass = (active: boolean) =>
    cn(
      'rounded-md text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
      'flex w-full min-w-0 items-center gap-1 px-2 py-2 text-left font-medium',
      active
        ? 'bg-accent text-accent-foreground'
        : 'text-foreground hover:bg-muted/60',
    )

  const projectUnderWorkspaceClass = (active: boolean) =>
    cn(
      'rounded-md text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
      'flex w-full min-w-0 items-center py-1.5 pr-2 pl-7 text-left',
      active
        ? 'bg-accent font-medium text-accent-foreground'
        : 'text-muted-foreground hover:bg-muted/50 hover:text-foreground',
    )

  return (
    <>
      <ShellSidebar
        storageKey={STORAGE_EXPANDED}
        asideAriaLabel="Platform"
        headerLeading={
          <NavLink
            to={headerTo}
            title="Backfield"
            aria-label="Backfield"
            className={cn(
              'flex min-w-0 flex-1 items-center rounded-md px-1 py-1 -ml-1',
              'hover:bg-muted/35 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
            )}
          >
            <span className="truncate text-sm font-semibold tracking-tight text-foreground">
              Backfield
            </span>
          </NavLink>
        }
      >
        {(expanded: boolean, { expand }: { expand: () => void }) => (
          <nav className="flex flex-col flex-1 min-h-0 p-2 gap-0">
            <div className="flex-1 min-h-0 overflow-y-auto flex flex-col gap-2">
              {expanded ? (
                <div className={sectionTitleClass}>
                  <AgateProductMark className="size-4 stroke-[1.75]" />
                  <span>Agate</span>
                </div>
              ) : (
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="w-full h-9 shrink-0"
                  onClick={() => expand()}
                  title="Agate — workspaces"
                >
                  <AgateProductMark className="size-5 stroke-[1.75]" />
                </Button>
              )}

              {(expanded ? workspaceRows : []).map((ws) => {
                const workspaceExpanded = expandedWorkspaceSlugs.has(ws.slug)
                const wsContainsActiveProject = ws.projects.some(
                  (p) => p.slug === activeProjectSlug,
                )
                const wsHighlighted =
                  activeWorkspaceSlug === ws.slug || wsContainsActiveProject
                const projectsSorted = [...ws.projects].sort((a, b) =>
                  a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }),
                )
                const projectsPanelId = `sidebar-workspace-projects-${ws.slug}`
                return (
                  <div
                    key={`${ws.slug}-${ws.id}`}
                    className="flex flex-col gap-0.5"
                  >
                    <button
                      type="button"
                      title={ws.name}
                      aria-label={`${workspaceExpanded ? 'Collapse' : 'Expand'} ${ws.name}`}
                      aria-expanded={workspaceExpanded}
                      aria-controls={projectsPanelId}
                      onClick={() => toggleWorkspaceExpanded(ws.slug)}
                      className={workspaceRowClass(wsHighlighted)}
                    >
                      {workspaceExpanded ? (
                        <ChevronDown className="h-4 w-4 shrink-0 opacity-70" aria-hidden />
                      ) : (
                        <ChevronRight className="h-4 w-4 shrink-0 opacity-70" aria-hidden />
                      )}
                      <span className="min-w-0 truncate">{ws.name}</span>
                    </button>
                    {workspaceExpanded ? (
                      <div id={projectsPanelId} className="flex flex-col gap-0.5">
                        {projectsSorted.map((p) => {
                          const pActive = activeProjectSlug === p.slug
                          return (
                            <NavLink
                              key={`${ws.slug}-p-${p.id}`}
                              to={`/project/${encodeURIComponent(p.slug)}`}
                              title={p.name}
                              aria-label={`Open project ${p.name}`}
                              aria-current={pActive ? 'page' : undefined}
                              className={() => projectUnderWorkspaceClass(pActive)}
                            >
                              <span className="min-w-0 truncate">{p.name}</span>
                            </NavLink>
                          )
                        })}
                      </div>
                    ) : null}
                  </div>
                )
              })}

              {!workspaceAccess && expanded ? (
                <div className="px-2 py-1.5 text-sm text-muted-foreground select-none">
                  No workspaces available
                </div>
              ) : null}

              {sortedStylebooks.length > 0 ? (
                <>
                  <div className="border-t border-border/50 my-1" />
                  {expanded ? (
                    <div className={sectionTitleClass}>
                      <StylebookProductMark className="size-4 stroke-[1.75]" />
                      <span>Stylebook</span>
                    </div>
                  ) : (
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="w-full h-9 shrink-0 text-lg"
                      onClick={() => expand()}
                      title="Stylebook"
                    >
                      <StylebookProductMark className="size-5 stroke-[1.75]" />
                    </Button>
                  )}
                  {(expanded ? sortedStylebooks : []).map((sb) => {
                    const projSlug =
                      stylebookProjectSlug ??
                      pickProjectSlugForStylebookLinks(null, workspaceRows)
                    const openHref = stylebookShellHref(sb.slug, projSlug ?? undefined)

                    return (
                      <a
                        key={sb.id}
                        href={openHref}
                        className={cn(
                          'rounded-md text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                          'flex w-full min-w-0 items-center justify-between gap-2 px-2 py-2 text-left',
                          'text-foreground hover:bg-muted/60',
                        )}
                        title={sb.name}
                        aria-label={`Open ${sb.name} in Stylebook`}
                      >
                        <span className="min-w-0 truncate">{sb.name}</span>
                        {sb.is_default ? (
                          <span className="shrink-0 rounded border border-border bg-background/80 px-1.5 py-0 text-[10px] font-medium text-muted-foreground">
                            Default
                          </span>
                        ) : null}
                      </a>
                    )
                  })}
                </>
              ) : null}
            </div>

            <div className="border-t border-border/50 pt-2 shrink-0 space-y-1">
              {isOrgAdmin ? (
                <NavLink
                  to="/settings"
                  className={hubLinkClass}
                  title={!expanded ? 'Settings' : undefined}
                >
                  <Settings className="h-5 w-5 shrink-0" aria-hidden />
                  {expanded ? <span>Settings</span> : null}
                </NavLink>
              ) : null}
              <a
                href={helpHref()}
                className={hubLinkClass}
                title={!expanded ? 'Help' : undefined}
              >
                <HelpCircle className="h-5 w-5 shrink-0" aria-hidden />
                {expanded ? <span>Help</span> : null}
              </a>
            </div>
          </nav>
        )}
      </ShellSidebar>
    </>
  )
}
