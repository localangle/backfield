import { ReactNode, useEffect, useState } from "react"
import { NavLink, useNavigate, useSearchParams } from "react-router-dom"
import { BookOpen } from "lucide-react"
import {
  ShellProductBrand,
  ShellSidebar,
  UserAccountMenu,
  cn,
} from "@backfield/ui"
import { useAuth } from "@/lib/auth"
import { fetchProjects, type Project } from "@/lib/api"

interface LayoutProps {
  children: ReactNode
  headerContent?: ReactNode
}

export default function Layout({ children, headerContent }: LayoutProps) {
  const { username, logout } = useAuth()
  const [searchParams, setSearchParams] = useSearchParams()
  const [projects, setProjects] = useState<Project[]>([])
  const navigate = useNavigate()

  const projectSlug = searchParams.get("project") || ""
  const indexPath = projectSlug ? `/?project=${projectSlug}` : "/"

  useEffect(() => {
    fetchProjects()
      .then(setProjects)
      .catch((err) => console.error("Failed to fetch projects:", err))
  }, [])

  useEffect(() => {
    if (projects.length > 0 && !projectSlug) {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev)
        next.set("project", projects[0].slug)
        return next
      })
    }
  }, [projects, projectSlug, setSearchParams])

  const handleLogout = async () => {
    await logout()
    navigate("/login", { replace: true })
  }

  return (
    <div className="h-dvh min-h-0 bg-background flex flex-col overflow-hidden">
      <header className="border-b shrink-0">
        <div className="px-4 py-4 flex justify-between items-center">
          <ShellProductBrand
            to={indexPath}
            productTitle="Stylebook"
            platformSubtitle="Backfield Platform"
          />
          <div className="flex items-center gap-2">
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
