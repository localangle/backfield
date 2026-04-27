import { ReactNode, useEffect, useState } from "react"
import { useNavigate, useSearchParams } from "react-router-dom"
import { ShellProductBrand, UserAccountMenu } from "@backfield/ui"
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
    <div className="min-h-screen bg-background">
      <header className="border-b shrink-0 bg-background sticky top-0 z-[5000] overflow-visible">
        <div className="px-4 py-4 flex justify-between items-center overflow-visible">
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
      <main className="container relative z-0 mx-auto px-4 py-8 overflow-visible">{children}</main>
    </div>
  )
}
