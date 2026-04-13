import { useCallback, useEffect, useState } from 'react'
import { matchPath, NavLink, useLocation, useNavigate } from 'react-router-dom'
import {
  Building2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  HelpCircle,
  LayoutTemplate,
  Pencil,
  Plus,
  Settings,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import {
  createProject,
  deleteProject,
  listProjects,
  updateProject,
  type Project,
  type ProjectCreate,
} from '@/lib/api'
import ProjectDialog from '@/components/ProjectDialog'

const STORAGE_EXPANDED = 'agate-sidebar-expanded'
const STORAGE_PROJECTS_OPEN = 'agate-sidebar-projects-open'

export default function AppSidebar() {
  const location = useLocation()
  const navigate = useNavigate()
  const [expanded, setExpanded] = useState(() => readBool(STORAGE_EXPANDED, true))
  const [projectsOpen, setProjectsOpen] = useState(() => readBool(STORAGE_PROJECTS_OPEN, true))
  const [projects, setProjects] = useState<Project[]>([])
  const [projectDialogOpen, setProjectDialogOpen] = useState(false)
  const [editingProject, setEditingProject] = useState<Project | null>(null)

  const loadProjects = useCallback(async () => {
    try {
      const rows = await listProjects()
      setProjects(rows)
    } catch (e) {
      console.error(e)
    }
  }, [])

  useEffect(() => {
    loadProjects()
  }, [loadProjects, location.pathname])

  useEffect(() => {
    const onChanged = () => loadProjects()
    window.addEventListener('agate:projects-changed', onChanged)
    return () => window.removeEventListener('agate:projects-changed', onChanged)
  }, [loadProjects])

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_EXPANDED, String(expanded))
    } catch {
      /* ignore */
    }
  }, [expanded])

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_PROJECTS_OPEN, String(projectsOpen))
    } catch {
      /* ignore */
    }
  }, [projectsOpen])

  const toggleSidebar = useCallback(() => setExpanded((e) => !e), [])
  const toggleProjects = useCallback(() => setProjectsOpen((o) => !o), [])

  const openNewProject = () => {
    setEditingProject(null)
    setProjectDialogOpen(true)
  }

  const openEditProject = (p: Project) => {
    setEditingProject(p)
    setProjectDialogOpen(true)
  }

  const handleSaveProject = async (data: ProjectCreate) => {
    if (editingProject) {
      await updateProject(editingProject.id, { name: data.name })
      await loadProjects()
      window.dispatchEvent(new CustomEvent('agate:projects-changed'))
    } else {
      const p = await createProject(data)
      await loadProjects()
      window.dispatchEvent(new CustomEvent('agate:projects-changed'))
      navigate(`/project/${encodeURIComponent(p.slug)}`)
    }
  }

  const handleDeleteProject = async (p: Project) => {
    await deleteProject(p.id)
    await loadProjects()
    window.dispatchEvent(new CustomEvent('agate:projects-changed'))
    const m = matchPath({ path: '/project/:projectSlug', end: true }, location.pathname)
    const routeSlug =
      m?.params.projectSlug != null ? decodeURIComponent(m.params.projectSlug) : null
    if (routeSlug === p.slug) {
      const next = await listProjects()
      const def = next.find((x) => x.slug === 'general') ?? next[0]
      navigate(def ? `/project/${encodeURIComponent(def.slug)}` : '/')
    }
  }

  const hubLinkClass = ({ isActive }: { isActive: boolean }) =>
    cn(
      'flex items-center gap-3 rounded-md px-2 py-2 text-sm font-medium transition-colors',
      'hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
      isActive ? 'bg-muted text-foreground' : 'text-muted-foreground hover:text-foreground'
    )

  const projectRouteMatch = matchPath(
    { path: '/project/:projectSlug', end: true },
    location.pathname
  )
  const activeProjectSlug =
    projectRouteMatch?.params.projectSlug != null
      ? decodeURIComponent(projectRouteMatch.params.projectSlug)
      : null

  return (
    <>
      <aside
        className={cn(
          'flex flex-col border-r bg-muted/30 shrink-0 min-h-0 self-stretch transition-[width] duration-200 ease-out',
          expanded ? 'w-56' : 'w-14'
        )}
        aria-label="Main navigation"
      >
        <div className="flex items-center justify-end p-2 border-b border-border/50">
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-8 w-8 shrink-0"
            onClick={toggleSidebar}
            aria-expanded={expanded}
            aria-label={expanded ? 'Collapse sidebar' : 'Expand sidebar'}
          >
            {expanded ? <ChevronLeft className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          </Button>
        </div>

        <nav className="flex flex-col gap-1 p-2 flex-1 min-h-0">
          <div>
            {expanded ? (
              <button
                type="button"
                onClick={toggleProjects}
                className={cn(
                  'flex items-center justify-between w-full rounded-md px-2 py-2 text-sm font-medium',
                  'text-muted-foreground hover:bg-muted hover:text-foreground'
                )}
                aria-expanded={projectsOpen}
              >
                <span className="flex items-center gap-2">
                  <Building2 className="h-5 w-5 shrink-0" aria-hidden />
                  Projects
                </span>
                <ChevronDown
                  className={cn('h-4 w-4 transition-transform', !projectsOpen && '-rotate-90')}
                />
              </button>
            ) : (
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="w-full h-9"
                onClick={() => {
                  setExpanded(true)
                  setProjectsOpen(true)
                }}
                title="Projects"
              >
                <Building2 className="h-5 w-5" />
              </Button>
            )}

            {expanded && projectsOpen && (
              <div className="mt-1 ml-1 space-y-0.5 max-h-[40vh] overflow-y-auto pr-1">
                {projects.map((p) => (
                  <div key={p.id} className="flex items-center gap-0.5 group">
                    <NavLink
                      to={`/project/${encodeURIComponent(p.slug)}`}
                      className={() =>
                        cn(
                          'flex-1 truncate rounded-md px-2 py-1.5 text-sm transition-colors',
                          activeProjectSlug === p.slug
                            ? 'bg-background text-foreground font-medium shadow-sm'
                            : 'text-muted-foreground hover:bg-muted hover:text-foreground'
                        )
                      }
                      title={p.name}
                    >
                      {p.name}
                    </NavLink>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7 shrink-0 opacity-0 group-hover:opacity-100 text-muted-foreground"
                      title="Rename project"
                      onClick={() => openEditProject(p)}
                    >
                      <Pencil className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                ))}
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
              </div>
            )}
          </div>

          <div className="flex-1 min-h-2" />

          <div className="border-t border-border/50 pt-2 space-y-1">
            <NavLink
              to="/templates"
              className={hubLinkClass}
              title={!expanded ? 'Templates' : undefined}
            >
              <LayoutTemplate className="h-5 w-5 shrink-0" aria-hidden />
              {expanded && <span>Templates</span>}
            </NavLink>
            <NavLink
              to="/help"
              className={hubLinkClass}
              title={!expanded ? 'Help' : undefined}
            >
              <HelpCircle className="h-5 w-5 shrink-0" aria-hidden />
              {expanded && <span>Help</span>}
            </NavLink>
            <NavLink
              to="/settings"
              className={hubLinkClass}
              title={!expanded ? 'Settings' : undefined}
            >
              <Settings className="h-5 w-5 shrink-0" aria-hidden />
              {expanded && <span>Settings</span>}
            </NavLink>
          </div>
        </nav>
      </aside>

      <ProjectDialog
        open={projectDialogOpen}
        onOpenChange={setProjectDialogOpen}
        project={editingProject}
        onSave={handleSaveProject}
        onDelete={editingProject ? handleDeleteProject : undefined}
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
