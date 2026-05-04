import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  matchPath,
  NavLink,
  useLocation,
  useNavigate,
} from 'react-router-dom'
import {
  BookOpen,
  FolderKanban,
  HelpCircle,
  Newspaper,
  Plus,
} from 'lucide-react'
import { ShellSidebar } from '@backfield/ui'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { createProject, listProjects, type Project, type ProjectCreate } from '@/lib/api'
import ProjectDialog from '@/components/ProjectDialog'
import { useAuth } from '@/lib/auth'
import { listMyWorkspaces, type WorkspaceWithProjects } from '@/lib/core-api'
import { hasWorkspaceAccess } from '@/lib/workspace-access'
import { helpHref, stylebookShellHref } from '@/lib/platformUrls'
import {
  listStylebookCatalogs,
  type StylebookCatalogRow,
} from '@/lib/stylebook-org-api'

const STORAGE_EXPANDED = 'agate-sidebar-expanded'

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
  const navigate = useNavigate()
  const { organizationId, isOrgAdmin } = useAuth()
  const [workspaceRows, setWorkspaceRows] = useState<WorkspaceWithProjects[]>([])
  const [apiProjects, setApiProjects] = useState<Project[]>([])
  const [stylebooks, setStylebooks] = useState<StylebookCatalogRow[]>([])
  const [projectDialogOpen, setProjectDialogOpen] = useState(false)

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

  const openNewProject = () => setProjectDialogOpen(true)

  const handleSaveProject = async (data: ProjectCreate) => {
    const p = await createProject(data)
    await loadWorkspaces()
    await loadProjects()
    window.dispatchEvent(new CustomEvent('agate:projects-changed'))
    navigate(`/project/${encodeURIComponent(p.slug)}`)
  }

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

  const activeProjectName = useMemo(() => {
    if (!activeProjectSlug) return null
    for (const ws of workspaceRows) {
      const p = ws.projects.find((x) => x.slug === activeProjectSlug)
      if (p) return p.name
    }
    const ap = apiProjects.find((x) => x.slug === activeProjectSlug)
    return ap?.name ?? activeProjectSlug
  }, [activeProjectSlug, workspaceRows, apiProjects])

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

  const headerTitle = activeProjectName ?? 'Backfield'
  const headerTo =
    activeProjectSlug != null
      ? `/project/${encodeURIComponent(activeProjectSlug)}`
      : '/'

  const sectionTitleClass =
    'flex items-center gap-2 px-2 py-2 text-xs font-medium text-muted-foreground'

  const workspaceRowClass = (active: boolean) =>
    cn(
      'rounded-md text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
      'flex min-w-0 flex-1 items-center px-2 py-2 text-left',
      active
        ? 'bg-accent text-accent-foreground'
        : 'text-foreground hover:bg-muted/60',
    )

  return (
    <>
      <ShellSidebar
        storageKey={STORAGE_EXPANDED}
        asideAriaLabel="Platform"
        headerLeading={
          <NavLink
            to={headerTo}
            title={headerTitle}
            aria-label={
              activeProjectName
                ? `Active project: ${activeProjectName}`
                : 'Backfield'
            }
            className={cn(
              'flex min-w-0 flex-1 items-center gap-2 rounded-md px-1 py-1 -ml-1',
              'hover:bg-muted/35 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
            )}
          >
            <FolderKanban
              className="h-4 w-4 shrink-0 text-muted-foreground"
              aria-hidden
            />
            <span className="truncate text-sm font-semibold tracking-tight text-foreground">
              {headerTitle}
            </span>
          </NavLink>
        }
      >
        {(expanded: boolean, { expand }: { expand: () => void }) => (
          <nav className="flex flex-col flex-1 min-h-0 p-2 gap-0">
            <div className="flex-1 min-h-0 overflow-y-auto flex flex-col gap-2">
              {expanded ? (
                <div className={sectionTitleClass}>
                  <Newspaper className="h-4 w-4 shrink-0" aria-hidden />
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
                  <Newspaper className="h-5 w-5" aria-hidden />
                </Button>
              )}

              {(expanded ? workspaceRows : []).map((ws) => {
                const wsActive = activeWorkspaceSlug === ws.slug
                return (
                  <NavLink
                    key={`${ws.slug}-${ws.id}`}
                    to={`/workspace/${encodeURIComponent(ws.slug)}`}
                    title={ws.name}
                    aria-label={`Open workspace ${ws.name}`}
                    aria-current={wsActive ? 'page' : undefined}
                    className={() => workspaceRowClass(wsActive)}
                  >
                    <span className="min-w-0 truncate">{ws.name}</span>
                  </NavLink>
                )
              })}

              {expanded && workspaceAccess ? (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="w-full justify-start gap-2 h-8 text-muted-foreground"
                  onClick={openNewProject}
                >
                  <Plus className="h-4 w-4" />
                  New project
                </Button>
              ) : null}

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
                      <BookOpen className="h-4 w-4 shrink-0" aria-hidden />
                      <span>Stylebooks</span>
                    </div>
                  ) : (
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="w-full h-9 shrink-0"
                      onClick={() => expand()}
                      title="Stylebooks"
                    >
                      <BookOpen className="h-5 w-5" aria-hidden />
                    </Button>
                  )}
                  {(expanded ? sortedStylebooks : []).map((sb) => {
                    const projSlug =
                      stylebookProjectSlug ??
                      pickProjectSlugForStylebookLinks(null, workspaceRows)
                    const disabled = projSlug == null
                    const openHref =
                      projSlug != null
                        ? stylebookShellHref(projSlug, sb.slug)
                        : '#'

                    return (
                      <a
                        key={sb.id}
                        href={disabled ? undefined : openHref}
                        className={cn(
                          'rounded-md text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                          'flex w-full min-w-0 items-center justify-between gap-2 px-2 py-2 text-left',
                          disabled
                            ? 'pointer-events-none opacity-45 text-muted-foreground'
                            : 'text-foreground hover:bg-muted/60',
                        )}
                        title={
                          disabled
                            ? 'Open a workspace and pick a project first'
                            : sb.name
                        }
                        aria-label={sb.name}
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

      <ProjectDialog
        open={projectDialogOpen}
        onOpenChange={setProjectDialogOpen}
        project={null}
        onSave={handleSaveProject}
      />
    </>
  )
}
