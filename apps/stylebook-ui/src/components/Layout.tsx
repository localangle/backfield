import { ReactNode, useCallback, useEffect, useMemo, useState } from "react"
import {
  NavLink,
  useLocation,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom"
import { ChevronDown, ChevronRight, HelpCircle, Settings } from "lucide-react"
import {
  AgateProductMark,
  ShellProductBrand,
  ShellSidebar,
  StylebookProductMark,
  UserAccountMenu,
  cn,
} from "@backfield/ui"
import { useAuth } from "@/lib/auth"
import { fetchMe, listMyWorkspaces, type WorkspaceWithProjects } from "@/lib/core-api"
import { fetchProjects, type Project } from "@/lib/api"
import {
  fetchOrganizationStylebooks,
  type OrgStylebookRow,
} from "@/lib/stylebook-api/orgStylebooks"
import { fetchStylebookPermissions } from "@/lib/stylebook-api/permissions"
import {
  agateProjectHref,
  agateUiOrigin,
  agateWorkspaceHref,
  helpHref,
} from "@/lib/platformUrls"
import { hasWorkspaceAccess } from "@/lib/workspace-access"
import { StylebookEditProvider } from "@/lib/stylebookEditContext"
import { StylebookScopeProvider } from "@/lib/stylebookScopeContext"
import {
  parseLegacyStylebookQuery,
  stripLegacyStylebookFromSearch,
  stylebookCatalogBasePath,
} from "@/lib/stylebookPaths"

function projectSearchSuffix(searchParams: URLSearchParams): string {
  const p = new URLSearchParams()
  const scope = searchParams.get("project_scope")
  const filt = searchParams.get("project")
  if (scope) p.set("project_scope", scope)
  if (filt) p.set("project", filt)
  const s = p.toString()
  return s ? `?${s}` : ""
}

/** Default Agate project for catalog workflow when the URL omits scope (sidebar + dashboard stats). */
function defaultWorkflowProjectSlug(projects: Project[]): string {
  const preferred = projects.find((p) => p.slug === "general")
  return preferred?.slug ?? projects[0]?.slug ?? ""
}

const STORAGE_WORKSPACES_EXPANDED = "stylebook-sidebar-workspaces-expanded"

function readExpandedWorkspaceSlugs(): Set<string> {
  try {
    const raw = localStorage.getItem(STORAGE_WORKSPACES_EXPANDED)
    if (!raw) return new Set()
    const parsed = JSON.parse(raw) as unknown
    if (!Array.isArray(parsed)) return new Set()
    return new Set(parsed.filter((slug): slug is string => typeof slug === "string"))
  } catch {
    return new Set()
  }
}

interface LayoutProps {
  children: ReactNode
  headerContent?: ReactNode
}

export default function Layout({ children, headerContent }: LayoutProps) {
  const { username, logout, isOrgAdmin } = useAuth()
  const agateBase = agateUiOrigin()
  const location = useLocation()
  const params = useParams<{ stylebookSlug?: string }>()
  const [searchParams, setSearchParams] = useSearchParams()
  const [projects, setProjects] = useState<Project[]>([])
  const [workspaceRows, setWorkspaceRows] = useState<WorkspaceWithProjects[]>(
    [],
  )
  const [stylebooks, setStylebooks] = useState<OrgStylebookRow[]>([])
  const [canEditStylebook, setCanEditStylebook] = useState(false)
  const [orgId, setOrgId] = useState<number | null>(null)
  const [expandedWorkspaceSlugs, setExpandedWorkspaceSlugs] = useState<Set<string>>(
    readExpandedWorkspaceSlugs,
  )
  const navigate = useNavigate()

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

  /** Matches catalogNavigation: workflow scope from `project_scope` or `project`. */
  const workflowProjectSlug =
    searchParams.get("project_scope") || searchParams.get("project") || ""
  const routeSlug = (params.stylebookSlug ?? "").trim()

  const projectQs = useMemo(
    () => projectSearchSuffix(searchParams),
    [searchParams],
  )

  const sortedStylebooks = useMemo(() => {
    return [...stylebooks].sort(
      (a, b) =>
        Number(b.is_default) - Number(a.is_default) ||
        a.name.localeCompare(b.name),
    )
  }, [stylebooks])

  const effectiveStylebookSlug = useMemo(() => {
    if (stylebooks.length === 0) return ""
    if (routeSlug && stylebooks.some((b) => b.slug === routeSlug)) {
      return routeSlug
    }
    const preferred = stylebooks.find((b) => b.is_default)
    return preferred?.slug ?? stylebooks[0].slug
  }, [routeSlug, stylebooks])

  const indexPath = useMemo(() => {
    const slugForHome = routeSlug || effectiveStylebookSlug
    if (!slugForHome) return `/stylebook/default${projectQs}`
    return `${stylebookCatalogBasePath(slugForHome)}${projectQs}`
  }, [routeSlug, effectiveStylebookSlug, projectQs])

  const selectedStylebookLabel = useMemo(() => {
    if (!effectiveStylebookSlug) return "Stylebook"
    const row = stylebooks.find((b) => b.slug === effectiveStylebookSlug)
    const name = row?.name?.trim()
    if (name) return name
    return effectiveStylebookSlug
  }, [effectiveStylebookSlug, stylebooks])

  useEffect(() => {
    if (!effectiveStylebookSlug) {
      setCanEditStylebook(false)
      return
    }
    let cancelled = false
    void (async () => {
      try {
        const res = await fetchStylebookPermissions(effectiveStylebookSlug)
        if (!cancelled) setCanEditStylebook(Boolean(res.can_edit))
      } catch {
        if (!cancelled) setCanEditStylebook(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [effectiveStylebookSlug])

  const activeWorkspaceSlug = useMemo(() => {
    if (!workflowProjectSlug) return null
    for (const ws of workspaceRows) {
      if (ws.projects.some((p) => p.slug === workflowProjectSlug)) return ws.slug
    }
    return null
  }, [workflowProjectSlug, workspaceRows])

  useEffect(() => {
    const slugsToExpand = new Set<string>()
    if (activeWorkspaceSlug) slugsToExpand.add(activeWorkspaceSlug)
    if (workflowProjectSlug) {
      for (const ws of workspaceRows) {
        if (ws.projects.some((p) => p.slug === workflowProjectSlug)) {
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
  }, [activeWorkspaceSlug, workflowProjectSlug, workspaceRows])

  const workspaceAccess = hasWorkspaceAccess(workspaceRows, isOrgAdmin)

  useEffect(() => {
    fetchProjects()
      .then(setProjects)
      .catch((err) => console.error("Failed to fetch projects:", err))
  }, [])

  const loadWorkspaces = useCallback(async () => {
    try {
      const rows = await listMyWorkspaces()
      setWorkspaceRows(rows)
    } catch (err) {
      console.error("Failed to fetch workspaces:", err)
      setWorkspaceRows([])
    }
  }, [])

  useEffect(() => {
    void loadWorkspaces()
  }, [loadWorkspaces, location.pathname])

  useEffect(() => {
    const onChanged = () => {
      void loadWorkspaces()
    }
    window.addEventListener("agate:projects-changed", onChanged)
    window.addEventListener("agate:workspaces-changed", onChanged)
    return () => {
      window.removeEventListener("agate:projects-changed", onChanged)
      window.removeEventListener("agate:workspaces-changed", onChanged)
    }
  }, [loadWorkspaces])

  useEffect(() => {
    void fetchMe()
      .then((me) => {
        if (me.organization_id != null) setOrgId(me.organization_id)
      })
      .catch((err) => console.error("Failed to fetch session:", err))
  }, [])

  useEffect(() => {
    if (orgId == null) return
    void fetchOrganizationStylebooks(orgId)
      .then(setStylebooks)
      .catch((err) => console.error("Failed to fetch stylebooks:", err))
  }, [orgId])

  /** Every stylebook catalog URL keeps workflow project scope in the query (``project_scope=``). */
  useEffect(() => {
    if (!routeSlug || projects.length === 0 || workflowProjectSlug) return
    const slug = defaultWorkflowProjectSlug(projects)
    if (!slug) return
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        next.set("project_scope", slug)
        return next
      },
      { replace: true },
    )
  }, [routeSlug, projects, workflowProjectSlug, setSearchParams])

  /** Drop legacy ``?stylebook=`` when the slug already lives in the path. */
  useEffect(() => {
    if (!parseLegacyStylebookQuery(location.search)) return
    navigate(`${location.pathname}${stripLegacyStylebookFromSearch(location.search)}`, {
      replace: true,
    })
  }, [location.pathname, location.search, navigate])

  /** Unknown catalog slug → organization default (or first stylebook). */
  useEffect(() => {
    if (stylebooks.length === 0 || !routeSlug) return
    const known = stylebooks.some((b) => b.slug === routeSlug)
    if (known) return
    const nextSlug =
      stylebooks.find((b) => b.is_default)?.slug ?? stylebooks[0]?.slug ?? ""
    if (!nextSlug) return
    navigate(
      `/stylebook/${encodeURIComponent(nextSlug)}${projectSearchSuffix(searchParams)}`,
      { replace: true },
    )
  }, [routeSlug, stylebooks, navigate, searchParams])

  const onStylebookChange = useCallback(
    (slug: string) => {
      navigate(
        `/stylebook/${encodeURIComponent(slug)}${projectSearchSuffix(searchParams)}`,
      )
    },
    [navigate, searchParams],
  )

  const handleLogout = async () => {
    await logout()
    navigate("/login", { replace: true })
  }

  const sectionTitleClass =
    "flex items-center gap-2 px-2 py-2 text-xs font-medium text-muted-foreground"

  const workspaceRowClass = (active: boolean) =>
    cn(
      "rounded-md text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
      "flex w-full min-w-0 items-center gap-1 px-2 py-2 text-left font-medium",
      active
        ? "bg-accent text-accent-foreground"
        : "text-foreground hover:bg-muted/60",
    )

  const projectUnderWorkspaceClass = (active: boolean) =>
    cn(
      "rounded-md text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
      "flex w-full min-w-0 items-center py-1.5 pr-2 pl-7 text-left",
      active
        ? "bg-accent font-medium text-accent-foreground"
        : "text-muted-foreground hover:bg-muted/50 hover:text-foreground",
    )

  const stylebookRowClass = (active: boolean) =>
    cn(
      "rounded-md text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
      "flex w-full min-w-0 items-center justify-between gap-2 px-2 py-2 text-left font-normal",
      active
        ? "bg-accent text-accent-foreground"
        : "text-foreground hover:bg-muted/60",
    )

  const help = helpHref()

  return (
    <div className="h-dvh min-h-0 bg-background flex flex-col overflow-hidden">
      <header className="border-b shrink-0">
        <div className="px-4 py-4 flex justify-between items-center gap-3 flex-wrap">
          <ShellProductBrand
            to={indexPath}
            productMark={<StylebookProductMark />}
            productTitle="Stylebook"
            platformSubtitle="Backfield Platform"
          />
          <div className="flex items-center gap-2 flex-wrap justify-end flex-1 min-w-0">
            {headerContent}
            {username ? (
              <UserAccountMenu
                userLabel={username}
                isOrgAdmin={isOrgAdmin}
                onChangePassword={() => {
                  window.location.assign(`${agateBase}/account/password`)
                }}
                onManageUsers={
                  isOrgAdmin
                    ? () => {
                        window.location.assign(`${agateBase}/admin/users`)
                      }
                    : undefined
                }
                onManageCatalogs={
                  isOrgAdmin
                    ? () => {
                        window.location.assign(`${agateBase}/admin/stylebooks`)
                      }
                    : undefined
                }
                onLogout={() => void handleLogout()}
              />
            ) : null}
          </div>
        </div>
      </header>
      <div className="flex flex-1 min-h-0">
        <ShellSidebar
          storageKey="stylebook-sidebar-expanded"
          asideAriaLabel="Platform"
          headerLeading={
            <NavLink
              to={indexPath}
              title="Backfield"
              aria-label="Backfield"
              className={({ isActive }) =>
                cn(
                  "flex min-w-0 flex-1 items-center rounded-md px-1 py-1 -ml-1",
                  "hover:bg-muted/35 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  isActive && "bg-transparent",
                )
              }
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
                    <AgateProductMark className="size-4 text-[1.125rem]" />
                    <span>Agate</span>
                  </div>
                ) : (
                  <button
                    type="button"
                    title="Agate — workspaces"
                    className={cn(
                      "inline-flex h-9 w-full items-center justify-center rounded-md",
                      "hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                    )}
                    onClick={() => expand()}
                  >
                    <AgateProductMark className="size-5 text-[1.35rem]" />
                  </button>
                )}

                {(expanded ? workspaceRows : []).map((ws) => {
                  const workspaceExpanded = expandedWorkspaceSlugs.has(ws.slug)
                  const wsContainsActiveProject = ws.projects.some(
                    (p) => p.slug === workflowProjectSlug,
                  )
                  const wsHighlighted =
                    activeWorkspaceSlug === ws.slug || wsContainsActiveProject
                  const projectsSorted = [...ws.projects].sort((a, b) =>
                    a.name.localeCompare(b.name, undefined, { sensitivity: "base" }),
                  )
                  const projectsPanelId = `sidebar-workspace-projects-${ws.slug}`
                  return (
                    <div
                      key={`${ws.slug}-${ws.id}`}
                      className="flex flex-col gap-0.5"
                    >
                      <div
                        className={cn(
                          workspaceRowClass(wsHighlighted),
                          "gap-0 p-0",
                        )}
                      >
                        <button
                          type="button"
                          title={workspaceExpanded ? "Collapse" : "Expand"}
                          aria-label={`${workspaceExpanded ? "Collapse" : "Expand"} ${ws.name}`}
                          aria-expanded={workspaceExpanded}
                          aria-controls={projectsPanelId}
                          onClick={() => toggleWorkspaceExpanded(ws.slug)}
                          className={cn(
                            "inline-flex h-9 w-8 shrink-0 items-center justify-center rounded-md",
                            "hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                          )}
                        >
                          {workspaceExpanded ? (
                            <ChevronDown
                              className="h-4 w-4 shrink-0 opacity-70"
                              aria-hidden
                            />
                          ) : (
                            <ChevronRight
                              className="h-4 w-4 shrink-0 opacity-70"
                              aria-hidden
                            />
                          )}
                        </button>
                        <a
                          href={agateWorkspaceHref(ws.slug)}
                          title={ws.name}
                          aria-label={`Open workspace ${ws.name} in Agate`}
                          className={cn(
                            "min-w-0 flex-1 truncate py-2 pr-2",
                            "hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-md",
                          )}
                        >
                          {ws.name}
                        </a>
                      </div>
                      {workspaceExpanded ? (
                        <div id={projectsPanelId} className="flex flex-col gap-0.5">
                          {projectsSorted.map((p) => {
                            const pActive = workflowProjectSlug === p.slug
                            return (
                              <a
                                key={`${ws.slug}-p-${p.id}`}
                                href={agateProjectHref(p.slug)}
                                title={p.name}
                                aria-label={`Open project ${p.name} in Agate`}
                                aria-current={pActive ? "true" : undefined}
                                className={projectUnderWorkspaceClass(pActive)}
                              >
                                <span className="min-w-0 truncate">{p.name}</span>
                              </a>
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
                      <button
                        type="button"
                        title="Stylebook"
                        className={cn(
                          "inline-flex h-9 w-full items-center justify-center rounded-md text-lg",
                          "hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                        )}
                        onClick={() => expand()}
                      >
                        <StylebookProductMark className="size-5 stroke-[1.75]" />
                      </button>
                    )}
                    {(expanded ? sortedStylebooks : []).map((sb) => {
                      const isActive = routeSlug === sb.slug
                      return (
                        <button
                          key={sb.id}
                          type="button"
                          title={sb.name}
                          aria-label={sb.name}
                          aria-current={isActive ? "true" : undefined}
                          onClick={() => onStylebookChange(sb.slug)}
                          className={stylebookRowClass(isActive)}
                        >
                          <span className="min-w-0 truncate">{sb.name}</span>
                          {sb.is_default ? (
                            <span className="shrink-0 rounded border border-border bg-background/80 px-1.5 py-0 text-[10px] font-medium text-muted-foreground">
                              Default
                            </span>
                          ) : null}
                        </button>
                      )
                    })}
                  </>
                ) : null}
              </div>

              <div className="border-t border-border/50 pt-2 shrink-0 flex flex-col gap-0">
                {isOrgAdmin ? (
                  <a
                    href={`${agateBase}/settings`}
                    className={cn(
                      "flex items-center gap-3 rounded-md px-2 py-2 text-sm font-medium transition-colors",
                      "hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                      "text-muted-foreground hover:text-foreground",
                    )}
                    title={!expanded ? "Settings" : undefined}
                  >
                    <Settings className="h-5 w-5 shrink-0" aria-hidden />
                    {expanded ? <span>Settings</span> : null}
                  </a>
                ) : null}
                <a
                  href={help}
                  className={cn(
                    "flex items-center gap-3 rounded-md px-2 py-2 text-sm font-medium transition-colors",
                    "hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                    "text-muted-foreground hover:text-foreground",
                  )}
                  title={!expanded ? "Help" : undefined}
                >
                  <HelpCircle className="h-5 w-5 shrink-0" aria-hidden />
                  {expanded ? <span>Help</span> : null}
                </a>
              </div>
            </nav>
          )}
        </ShellSidebar>
        <StylebookScopeProvider selectedStylebookLabel={selectedStylebookLabel}>
          <StylebookEditProvider canEditStylebook={canEditStylebook}>
            <main className="flex-1 min-w-0 min-h-0 overflow-y-auto overscroll-y-contain">
              <div className="w-full max-w-none px-4 sm:px-6 lg:px-8 py-8">
                {children}
              </div>
            </main>
          </StylebookEditProvider>
        </StylebookScopeProvider>
      </div>
    </div>
  )
}
