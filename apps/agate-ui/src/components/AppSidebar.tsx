import { useCallback, useEffect, useState } from 'react'
import { matchPath, NavLink, useLocation, useNavigate } from 'react-router-dom'
import {
  Building2,
  ChevronDown,
  HelpCircle,
  LayoutTemplate,
  Newspaper,
  Plus,
  SquarePen,
} from 'lucide-react'
import { ShellSidebar } from '@backfield/ui'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { createProject, listProjects, type ProjectCreate } from '@/lib/api'
import ProjectDialog from '@/components/ProjectDialog'
import { useAuth } from '@/lib/auth'
import { listMyWorkspaces, type WorkspaceWithProjects } from '@/lib/core-api'
import { hasWorkspaceAccess } from '@/lib/workspace-access'

const STORAGE_EXPANDED = 'agate-sidebar-expanded'
const STORAGE_WORKSPACES_OPEN = 'agate-sidebar-workspaces-open'

function isSidebarWorkspacePage(ws: WorkspaceWithProjects): boolean {
  return ws.id > 0 && ws.slug !== '_ungrouped'
}

export default function AppSidebar() {
  const location = useLocation()
  const navigate = useNavigate()
  const { organizationName, isOrgAdmin } = useAuth()
  const publicationLabel = organizationName ?? 'Workspaces'
  const [workspacesOpen, setWorkspacesOpen] = useState(() =>
    readBool(STORAGE_WORKSPACES_OPEN, true),
  )
  const [workspaceRows, setWorkspaceRows] = useState<WorkspaceWithProjects[]>([])
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

  useEffect(() => {
    void loadWorkspaces()
  }, [loadWorkspaces, location.pathname])

  useEffect(() => {
    const onChanged = () => void loadWorkspaces()
    window.addEventListener('agate:projects-changed', onChanged)
    window.addEventListener('agate:workspaces-changed', onChanged)
    return () => {
      window.removeEventListener('agate:projects-changed', onChanged)
      window.removeEventListener('agate:workspaces-changed', onChanged)
    }
  }, [loadWorkspaces])

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_WORKSPACES_OPEN, String(workspacesOpen))
    } catch {
      /* ignore */
    }
  }, [workspacesOpen])

  const toggleWorkspaces = useCallback(() => setWorkspacesOpen((o) => !o), [])

  const openNewProject = () => {
    setProjectDialogOpen(true)
  }

  const handleSaveProject = async (data: ProjectCreate) => {
    const p = await createProject(data)
    await loadWorkspaces()
    window.dispatchEvent(new CustomEvent('agate:projects-changed'))
    navigate(`/project/${encodeURIComponent(p.slug)}`)
  }

  const hubLinkClass = ({ isActive }: { isActive: boolean }) =>
    cn(
      'flex items-center gap-3 rounded-md px-2 py-2 text-sm font-medium transition-colors',
      'hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
      isActive ? 'bg-muted text-foreground' : 'text-muted-foreground hover:text-foreground',
    )

  const projectRouteMatch = matchPath(
    { path: '/project/:projectSlug', end: true },
    location.pathname,
  )
  const activeProjectSlug =
    projectRouteMatch?.params.projectSlug != null
      ? decodeURIComponent(projectRouteMatch.params.projectSlug)
      : null

  const workspaceAccess = hasWorkspaceAccess(workspaceRows, isOrgAdmin)

  return (
    <>
      <ShellSidebar
        storageKey={STORAGE_EXPANDED}
        headerLeading={
          <NavLink
            to="/"
            end
            title={publicationLabel}
            aria-label={`${publicationLabel} — all workspaces`}
            className={cn(
              'flex min-w-0 flex-1 items-center gap-2 rounded-md px-1 py-1 -ml-1',
              'hover:bg-muted/35 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
            )}
          >
            <Newspaper
              className="h-4 w-4 shrink-0 text-muted-foreground"
              aria-hidden
            />
            <span className="truncate text-sm font-semibold tracking-tight text-foreground">
              {publicationLabel}
            </span>
          </NavLink>
        }
      >
        {(expanded, { expand }) => (
        <nav className="flex flex-col gap-1 p-2 flex-1 min-h-0">
          <div>
            {expanded ? (
              <button
                type="button"
                onClick={toggleWorkspaces}
                className={cn(
                  'flex items-center justify-between w-full rounded-md px-2 py-2 text-sm font-medium',
                  'text-muted-foreground hover:bg-muted hover:text-foreground',
                )}
                aria-expanded={workspacesOpen}
              >
                <span className="flex items-center gap-2">
                  <Building2 className="h-5 w-5 shrink-0" aria-hidden />
                  Workspaces
                </span>
                <ChevronDown
                  className={cn('h-4 w-4 transition-transform', !workspacesOpen && '-rotate-90')}
                />
              </button>
            ) : (
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="w-full h-9"
                onClick={() => {
                  expand()
                  setWorkspacesOpen(true)
                }}
                title="Workspaces"
              >
                <Building2 className="h-5 w-5" />
              </Button>
            )}

            {expanded && workspacesOpen && (
              <div className="mt-1 space-y-3 max-h-[50vh] overflow-y-auto pr-1">
                {workspaceRows.map((ws) => (
                  <div key={`${ws.slug}-${ws.id}`}>
                    <div className="flex items-center gap-0.5 pr-0.5">
                      <div
                        className="min-w-0 flex-1 truncate px-2 py-0.5 text-[11px] font-semibold text-muted-foreground uppercase tracking-wide"
                        title={ws.name}
                      >
                        {ws.name}
                      </div>
                      {isSidebarWorkspacePage(ws) ? (
                        <NavLink
                          to={`/workspace/${encodeURIComponent(ws.slug)}`}
                          title={`${ws.name} — manage workspace`}
                          aria-label={`Open workspace ${ws.name}`}
                          className={({ isActive }) =>
                            cn(
                              'shrink-0 inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground/80 transition-colors',
                              'hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                              isActive && 'bg-muted text-foreground',
                            )
                          }
                        >
                          <SquarePen className="h-3.5 w-3.5" aria-hidden />
                        </NavLink>
                      ) : null}
                    </div>
                    <div className="mt-0.5 ml-1 space-y-0.5 border-l border-border/50 pl-2">
                      {ws.projects.map((p) => (
                        <NavLink
                          key={p.id}
                          to={`/project/${encodeURIComponent(p.slug)}`}
                          className={() =>
                            cn(
                              'block truncate rounded-md px-2 py-1.5 text-sm transition-colors',
                              activeProjectSlug === p.slug
                                ? 'bg-background text-foreground font-medium shadow-sm'
                                : 'text-muted-foreground hover:bg-muted hover:text-foreground',
                            )
                          }
                          title={p.name}
                        >
                          {p.name}
                        </NavLink>
                      ))}
                    </div>
                  </div>
                ))}
                {workspaceAccess ? (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="w-full justify-start gap-2 mt-1 h-8 text-muted-foreground"
                    onClick={openNewProject}
                  >
                    <Plus className="h-4 w-4" />
                    New project
                  </Button>
                ) : (
                  <div
                    className="mt-1 px-2 py-1.5 text-sm text-muted-foreground select-none"
                    aria-disabled="true"
                  >
                    None
                  </div>
                )}
              </div>
            )}
          </div>

          <div className="flex-1 min-h-2" />

          <div className="border-t border-border/50 pt-2 space-y-1">
            {workspaceAccess ? (
              <NavLink
                to="/templates"
                className={hubLinkClass}
                title={!expanded ? 'Templates' : undefined}
              >
                <LayoutTemplate className="h-5 w-5 shrink-0" aria-hidden />
                {expanded && <span>Templates</span>}
              </NavLink>
            ) : null}
            <NavLink
              to="/help"
              className={hubLinkClass}
              title={!expanded ? 'Help' : undefined}
            >
              <HelpCircle className="h-5 w-5 shrink-0" aria-hidden />
              {expanded && <span>Help</span>}
            </NavLink>
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

function readBool(key: string, defaultVal: boolean): boolean {
  try {
    const v = localStorage.getItem(key)
    if (v === null) return defaultVal
    return v === 'true'
  } catch {
    return defaultVal
  }
}
