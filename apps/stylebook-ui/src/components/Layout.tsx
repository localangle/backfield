import { ReactNode, useEffect, useState } from "react"
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom"
import { useAuth } from "@/lib/auth"
import { Button } from "@/components/ui/button"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { fetchProjects, type Project } from "@/lib/api"

interface LayoutProps {
  children: ReactNode
  headerContent?: ReactNode
}

export default function Layout({ children, headerContent }: LayoutProps) {
  const { username, logout } = useAuth()
  const [searchParams, setSearchParams] = useSearchParams()
  const [projects, setProjects] = useState<Project[]>([])
  const location = useLocation()
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

  const handleProjectChange = (slug: string) => {
    const pathname = location.pathname
    if (pathname.startsWith("/locations/")) {
      navigate(`/locations/candidates?project=${slug}`)
    } else if (pathname.startsWith("/people/")) {
      navigate(`/people/candidates?project=${slug}`)
    } else if (pathname.startsWith("/organizations/")) {
      navigate(`/organizations/candidates?project=${slug}`)
    } else if (pathname.startsWith("/works/")) {
      navigate(`/works/candidates?project=${slug}`)
    } else if (pathname.startsWith("/agents/")) {
      navigate(`${pathname}?project=${slug}`)
    } else {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev)
        next.set("project", slug)
        return next
      })
    }
  }

  const handleLogout = async () => {
    await logout()
    navigate("/login", { replace: true })
  }

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b bg-background sticky top-0 z-[100] overflow-visible">
        <div className="container mx-auto px-4 py-4 flex justify-between items-center overflow-visible">
          <Link to={indexPath} className="hover:opacity-80 transition-opacity">
            <h1 className="text-2xl font-bold">Backfield</h1>
            <p className="text-sm text-muted-foreground mt-1">Stylebook</p>
          </Link>
          <div className="flex items-center gap-4 relative">
            <div className="relative z-[200]">
              {projects.length > 0 ? (
                <Select value={projectSlug || undefined} onValueChange={handleProjectChange}>
                  <SelectTrigger className="w-[250px] min-w-[200px]">
                    <SelectValue placeholder="Select project" />
                  </SelectTrigger>
                  <SelectContent className="z-[200]" position="popper">
                    {projects.map((proj) => (
                      <SelectItem key={proj.id} value={proj.slug}>
                        {proj.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ) : null}
              {headerContent}
            </div>
            {username ? (
              <span className="text-sm text-muted-foreground max-w-[200px] truncate">{username}</span>
            ) : null}
            <Button variant="outline" size="sm" onClick={() => void handleLogout()}>
              Logout
            </Button>
          </div>
        </div>
      </header>
      <main className="container mx-auto px-4 py-8 overflow-visible">{children}</main>
    </div>
  )
}
