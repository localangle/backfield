import { ReactNode, useCallback, useEffect, useMemo, useState } from "react"
import { NavLink, useNavigate, useSearchParams } from "react-router-dom"
import {
  BookOpen,
  FolderKanban,
  HelpCircle,
  Newspaper,
} from "lucide-react"
import {
  ShellProductBrand,
  ShellSidebar,
  UserAccountMenu,
  cn,
} from "@backfield/ui"
import { useAuth } from "@/lib/auth"
import { fetchMe, listMyWorkspaces, type WorkspaceWithProjects } from "@/lib/core-api"
import { fetchProjects, type Project } from "@/lib/api"
import { STYLEBOOK_URL_QUERY_KEY } from "@/lib/stylebook-api/client"
import {
  fetchOrganizationStylebooks,
  type OrgStylebookRow,
} from "@/lib/stylebook-api/orgStylebooks"
import { agateUiOrigin, helpHref } from "@/lib/platformUrls"
import { StylebookScopeProvider } from "@/lib/stylebookScopeContext"

interface LayoutProps {
  children: ReactNode
  headerContent?: ReactNode
}

function defaultStylebookSlugForProject(
  projects: Project[],
  stylebooks: OrgStylebookRow[],
  projectSlug: string,
): string {
  if (!stylebooks.length) return ""
  const project = projects.find((x) => x.slug === projectSlug)
  const ws = project?.workspace_stylebook_slug
  if (ws && stylebooks.some((b) => b.slug === ws)) return ws
  const preferred = stylebooks.find((b) => b.is_default)
  return preferred?.slug ?? stylebooks[0].slug
}

export default function Layout({ children, headerContent }: LayoutProps) {
  const { username, logout, isOrgAdmin } = useAuth()
  const agateBase = agateUiOrigin()
  const [searchParams, setSearchParams] = useSearchParams()
  const [projects, setProjects] = useState<Project[]>([])
  const [workspaceRows, setWorkspaceRows] = useState<WorkspaceWithProjects[]>(
    [],
  )
  const [stylebooks, setStylebooks] = useState<OrgStylebookRow[]>([])
  const [orgId, setOrgId] = useState<number | null>(null)
  const navigate = useNavigate()

  const projectSlug = searchParams.get("project") || ""
  const stylebookSlug = searchParams.get(STYLEBOOK_URL_QUERY_KEY) || ""

  const indexQuery = useMemo(() => {
    const p = new URLSearchParams()
    if (projectSlug) p.set("project", projectSlug)
    if (stylebookSlug) p.set(STYLEBOOK_URL_QUERY_KEY, stylebookSlug)
    const s = p.toString()
    return s ? `?${s}` : ""
  }, [projectSlug, stylebookSlug])
  const indexPath = indexQuery ? `/${indexQuery}` : "/"

  const sortedStylebooks = useMemo(() => {
    return [...stylebooks].sort(
      (a, b) =>
        Number(b.is_default) - Number(a.is_default) ||
        a.name.localeCompare(b.name),
    )
  }, [stylebooks])

  const effectiveStylebookSlug = useMemo(() => {
    if (!projectSlug || stylebooks.length === 0) return ""
    if (stylebookSlug && stylebooks.some((b) => b.slug === stylebookSlug)) {
      return stylebookSlug
    }
    return defaultStylebookSlugForProject(projects, stylebooks, projectSlug)
  }, [projectSlug, stylebookSlug, stylebooks, projects])

  const activeProjectName = useMemo(() => {
    if (!projectSlug) return null
    const p = projects.find((x) => x.slug === projectSlug)
    return p?.name ?? projectSlug
  }, [projectSlug, projects])
  const activeProjectLabel = activeProjectName ?? "Backfield"

  const selectedStylebookLabel = useMemo(() => {
    if (!effectiveStylebookSlug) return "Stylebook"
    const row = stylebooks.find((b) => b.slug === effectiveStylebookSlug)
    const name = row?.name?.trim()
    if (name) return name
    return effectiveStylebookSlug
  }, [effectiveStylebookSlug, stylebooks])

  const activeWorkspaceSlug = useMemo(() => {
    if (!projectSlug) return null
    for (const ws of workspaceRows) {
      if (ws.projects.some((p) => p.slug === projectSlug)) return ws.slug
    }
    return null
  }, [projectSlug, workspaceRows])

  useEffect(() => {
    fetchProjects()
      .then(setProjects)
      .catch((err) => console.error("Failed to fetch projects:", err))
  }, [])

  useEffect(() => {
    void listMyWorkspaces()
      .then(setWorkspaceRows)
      .catch((err) => console.error("Failed to fetch workspaces:", err))
  }, [])

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

  useEffect(() => {
    if (projects.length > 0 && !projectSlug) {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev)
        next.set("project", projects[0].slug)
        return next
      })
    }
  }, [projects, projectSlug, setSearchParams])

  useEffect(() => {
    if (!projectSlug || stylebooks.length === 0) return

    if (stylebooks.length <= 1) {
      if (stylebookSlug) {
        setSearchParams(
          (prev) => {
            const next = new URLSearchParams(prev)
            next.delete(STYLEBOOK_URL_QUERY_KEY)
            return next
          },
          { replace: true },
        )
      }
      return
    }

    const known = stylebooks.some((b) => b.slug === stylebookSlug)
    if (known && stylebookSlug) return

    const nextSlug = defaultStylebookSlugForProject(
      projects,
      stylebooks,
      projectSlug,
    )
    if (!nextSlug || nextSlug === stylebookSlug) return

    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        next.set(STYLEBOOK_URL_QUERY_KEY, nextSlug)
        return next
      },
      { replace: true },
    )
  }, [projectSlug, stylebookSlug, stylebooks, projects, setSearchParams])

  const onStylebookChange = useCallback(
    (slug: string) => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev)
          next.set(STYLEBOOK_URL_QUERY_KEY, slug)
          return next
        },
        { replace: false },
      )
    },
    [setSearchParams],
  )

  const handleLogout = async () => {
    await logout()
    navigate("/login", { replace: true })
  }

  const sectionTitleClass =
    "flex items-center gap-2 px-2 py-2 text-xs font-medium text-muted-foreground"

  const agateWorkspaceRowClass = (active: boolean) =>
    cn(
      "rounded-md text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
      "flex w-full min-w-0 items-center px-2 py-2 text-left",
      active
        ? "bg-accent text-accent-foreground"
        : "text-foreground hover:bg-muted/60",
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
                        window.location.assign(`${agateBase}/admin/catalogs`)
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
              end
              title={activeProjectLabel}
              aria-label={
                activeProjectName
                  ? `Active project: ${activeProjectName}`
                  : "Backfield"
              }
              className={cn(
                "flex min-w-0 flex-1 items-center gap-2 rounded-md px-1 py-1 -ml-1",
                "hover:bg-muted/35 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              )}
            >
              <FolderKanban
                className="h-4 w-4 shrink-0 text-muted-foreground"
                aria-hidden
              />
              <span className="truncate text-sm font-semibold tracking-tight text-foreground">
                {activeProjectLabel}
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
                  <button
                    type="button"
                    title="Agate — workspaces"
                    className={cn(
                      "inline-flex h-9 w-full items-center justify-center rounded-md",
                      "hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                    )}
                    onClick={() => expand()}
                  >
                    <Newspaper className="h-5 w-5 text-muted-foreground" aria-hidden />
                  </button>
                )}

                {(expanded ? workspaceRows : []).map((ws) => {
                  const wsActive = activeWorkspaceSlug === ws.slug
                  const href = `${agateBase}/workspace/${encodeURIComponent(ws.slug)}`
                  return (
                    <a
                      key={`${ws.slug}-${ws.id}`}
                      href={href}
                      title={ws.name}
                      aria-label={`Open workspace ${ws.name} in Agate`}
                      aria-current={wsActive ? "page" : undefined}
                      className={agateWorkspaceRowClass(wsActive)}
                    >
                      <span className="min-w-0 truncate">{ws.name}</span>
                    </a>
                  )
                })}

                {sortedStylebooks.length > 0 ? (
                  <>
                    <div className="border-t border-border/50 my-1" />
                    {expanded ? (
                      <div className={sectionTitleClass}>
                        <BookOpen className="h-4 w-4 shrink-0" aria-hidden />
                        <span>Stylebooks</span>
                      </div>
                    ) : (
                      <button
                        type="button"
                        title="Stylebooks"
                        className={cn(
                          "inline-flex h-9 w-full items-center justify-center rounded-md",
                          "hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                        )}
                        onClick={() => expand()}
                      >
                        <BookOpen className="h-5 w-5 text-muted-foreground" aria-hidden />
                      </button>
                    )}
                    {(expanded ? sortedStylebooks : []).map((sb) => {
                      const isActive = effectiveStylebookSlug === sb.slug
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

              <div className="border-t border-border/50 pt-2 shrink-0">
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
          <main className="flex-1 min-w-0 overflow-auto">
            <div className="w-full max-w-none px-4 sm:px-6 lg:px-8 py-8">
              {children}
            </div>
          </main>
        </StylebookScopeProvider>
      </div>
    </div>
  )
}
