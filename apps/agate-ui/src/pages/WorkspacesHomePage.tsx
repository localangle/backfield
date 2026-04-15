import { useCallback, useEffect, useState } from "react"
import { Link } from "react-router-dom"
import { Loader2, FolderOpen } from "lucide-react"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { listMyWorkspaces, type WorkspaceWithProjects } from "@/lib/core-api"

function defaultProjectSlug(ws: WorkspaceWithProjects): string {
  const g = ws.projects.find((p) => p.slug === "general")
  if (g) return g.slug
  const sorted = [...ws.projects].sort((a, b) => a.slug.localeCompare(b.slug))
  return sorted[0]?.slug ?? ""
}

export default function WorkspacesHomePage() {
  const [rows, setRows] = useState<WorkspaceWithProjects[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setError(null)
    setLoading(true)
    try {
      const data = await listMyWorkspaces()
      setRows(data)
    } catch (e) {
      console.error(e)
      setError(e instanceof Error ? e.message : "Failed to load workspaces")
      setRows([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[40vh] gap-3">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        <p className="text-sm text-muted-foreground">Loading workspaces…</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="space-y-4 max-w-lg">
        <p className="text-destructive text-sm">{error}</p>
        <Button type="button" variant="outline" onClick={() => void load()}>
          Retry
        </Button>
      </div>
    )
  }

  if (rows.length === 0) {
    return (
      <div className="space-y-2">
        <h1 className="text-2xl font-semibold tracking-tight">Workspaces</h1>
        <p className="text-muted-foreground text-sm">
          You don&apos;t have access to any projects yet. Ask an organization admin to grant
          workspace access, or open Templates to explore flows.
        </p>
        <Button type="button" variant="outline" asChild>
          <Link to="/templates">Browse templates</Link>
        </Button>
      </div>
    )
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Workspaces</h1>
        <p className="text-muted-foreground text-sm mt-1 max-w-2xl">
          Open a workspace to work with its projects. Switch workspaces anytime from this page or
          the sidebar.
        </p>
      </div>

      <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {rows.map((ws) => {
          const primary = defaultProjectSlug(ws)
          const href = primary ? `/project/${encodeURIComponent(primary)}` : "/templates"
          return (
            <li key={`${ws.slug}-${ws.id}`}>
              <Card className="h-full flex flex-col hover:border-foreground/20 transition-colors">
                <CardHeader>
                  <div className="flex items-start gap-2">
                    <FolderOpen className="h-5 w-5 text-muted-foreground shrink-0 mt-0.5" />
                    <div className="min-w-0">
                      <CardTitle className="text-lg leading-snug">{ws.name}</CardTitle>
                      <CardDescription className="font-mono text-xs truncate">
                        {ws.slug}
                      </CardDescription>
                    </div>
                  </div>
                </CardHeader>
                <CardContent className="flex-1 flex flex-col gap-3">
                  <p className="text-sm text-muted-foreground">
                    {ws.projects.length} project{ws.projects.length === 1 ? "" : "s"}
                  </p>
                  <ul className="text-sm space-y-1 border-t border-border/60 pt-3">
                    {ws.projects.slice(0, 6).map((p) => (
                      <li key={p.id}>
                        <Link
                          to={`/project/${encodeURIComponent(p.slug)}`}
                          className="text-foreground hover:underline font-medium"
                        >
                          {p.name}
                        </Link>
                      </li>
                    ))}
                    {ws.projects.length > 6 ? (
                      <li className="text-xs text-muted-foreground">
                        +{ws.projects.length - 6} more
                      </li>
                    ) : null}
                  </ul>
                  <Button type="button" className="w-full mt-auto" asChild>
                    <Link to={href}>
                      {primary ? "Open workspace" : "Browse templates"}
                    </Link>
                  </Button>
                </CardContent>
              </Card>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
