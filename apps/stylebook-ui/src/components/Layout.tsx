import { ReactNode, useCallback, useEffect, useMemo, useState } from "react"
import { NavLink, useNavigate, useSearchParams } from "react-router-dom"
import { BookOpen } from "lucide-react"
import {
  ShellProductBrand,
  ShellSidebar,
  UserAccountMenu,
  cn,
} from "@backfield/ui"
import { useAuth } from "@/lib/auth"
import { fetchMe } from "@/lib/core-api"
import { fetchProjects, type Project } from "@/lib/api"
import { STYLEBOOK_URL_QUERY_KEY } from "@/lib/stylebook-api/client"
import {
  fetchOrganizationStylebooks,
  type OrgStylebookRow,
} from "@/lib/stylebook-api/orgStylebooks"

interface LayoutProps {
  children: ReactNode
  headerContent?: ReactNode
}

function defaultCatalogSlugForProject(
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
  const { username, logout } = useAuth()
  const [searchParams, setSearchParams] = useSearchParams()
  const [projects, setProjects] = useState<Project[]>([])
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
        Number(b.is_default) - Number(a.is_default) || a.name.localeCompare(b.name),
    )
  }, [stylebooks])

  useEffect(() => {
    fetchProjects()
      .then(setProjects)
      .catch((err) => console.error("Failed to fetch projects:", err))
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
      .catch((err) => console.error("Failed to fetch catalogs:", err))
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

    const nextSlug = defaultCatalogSlugForProject(projects, stylebooks, projectSlug)
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

  const onCatalogChange = useCallback(
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

  const showCatalogSwitcher = sortedStylebooks.length > 1

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
            {showCatalogSwitcher ? (
              <label className="flex items-center gap-2 text-sm min-w-0">
                <span className="text-muted-foreground shrink-0">Catalog</span>
                <select
                  className={cn(
                    "h-9 min-w-[10rem] max-w-[18rem] rounded-md border border-input bg-background px-2 py-1 text-sm",
                    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  )}
                  aria-label="Catalog"
                  value={stylebookSlug || defaultCatalogSlugForProject(projects, stylebooks, projectSlug)}
                  onChange={(e) => onCatalogChange(e.target.value)}
                >
                  {sortedStylebooks.map((sb) => (
                    <option key={sb.id} value={sb.slug}>
                      {sb.name}
                    </option>
                  ))}
                </select>
              </label>
            ) : null}
            {headerContent}
            {username ? (
              <UserAccountMenu
                userLabel={username}
                isOrgAdmin={false}
                onLogout={() => void handleLogout()}
              />
            ) : null}
          </div>
        </div>
      </header>
      <div className="flex flex-1 min-h-0">
        <ShellSidebar
          storageKey="stylebook-sidebar-expanded"
          headerLeading={
            <NavLink
              to={indexPath}
              end
              title="Stylebook"
              aria-label="Stylebook — home"
              className={cn(
                "flex min-w-0 flex-1 items-center gap-2 rounded-md px-1 py-1 -ml-1",
                "hover:bg-muted/35 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              )}
            >
              <BookOpen
                className="h-4 w-4 shrink-0 text-muted-foreground"
                aria-hidden
              />
              <span className="truncate text-sm font-semibold tracking-tight text-foreground">
                Stylebook
              </span>
            </NavLink>
          }
        >
          <nav
            className="flex flex-col gap-1 p-2 flex-1 min-h-0"
            aria-label="Stylebook"
          />
        </ShellSidebar>
        <main className="flex-1 min-w-0 overflow-auto">
          <div className="w-full max-w-none px-4 sm:px-6 lg:px-8 py-8">
            {children}
          </div>
        </main>
      </div>
    </div>
  )
}
