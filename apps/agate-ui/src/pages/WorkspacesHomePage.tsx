import { useCallback, useEffect, useRef, useState } from "react"
import { Link } from "react-router-dom"
import { FolderOpen, Loader2 } from "lucide-react"
import { AddPlusCta } from "@/components/AddPlusCta"
import { InlineNameEditor } from "@/components/InlineNameEditor"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useAuth } from "@/lib/auth"
import {
  createWorkspace,
  listMyWorkspaces,
  patchOrganization,
  type WorkspaceWithProjects,
} from "@/lib/core-api"
import { hasWorkspaceAccess } from "@/lib/workspace-access"

function defaultProjectSlug(ws: WorkspaceWithProjects): string {
  const g = ws.projects.find((p) => p.slug === "general")
  if (g) return g.slug
  const sorted = [...ws.projects].sort((a, b) => a.slug.localeCompare(b.slug))
  return sorted[0]?.slug ?? ""
}

type WorkspaceGridEntry =
  | { kind: "workspace"; ws: WorkspaceWithProjects }
  | { kind: "add" }

/** Workspace tiles in API order, with Add Workspace last when shown. */
function workspaceGridEntries(
  rows: WorkspaceWithProjects[],
  includeAdd: boolean,
): WorkspaceGridEntry[] {
  const mapped: WorkspaceGridEntry[] = rows.map((ws) => ({ kind: "workspace", ws }))
  if (!includeAdd) return mapped
  return [...mapped, { kind: "add" }]
}

function WorkspaceHomeCard({
  ws,
  canUseTemplates,
}: {
  ws: WorkspaceWithProjects
  canUseTemplates: boolean
}) {
  const primary = defaultProjectSlug(ws)
  const isRealWorkspace = ws.id > 0 && ws.slug !== "_ungrouped"
  const href = isRealWorkspace
    ? `/workspace/${encodeURIComponent(ws.slug)}`
    : primary
      ? `/project/${encodeURIComponent(primary)}`
      : canUseTemplates
        ? "/templates"
        : "/"
  const openLabel = isRealWorkspace
    ? "Open workspace"
    : primary
      ? "Open workspace"
      : canUseTemplates
        ? "Browse templates"
        : "Workspaces"
  return (
    <Card className="h-full w-full flex flex-col hover:border-foreground/20 transition-colors">
      <CardHeader>
        <div className="flex items-start gap-2">
          <FolderOpen className="h-5 w-5 text-muted-foreground shrink-0 mt-0.5" />
          <div className="min-w-0">
            <CardTitle className="text-lg leading-snug">{ws.name}</CardTitle>
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
            <li className="text-xs text-muted-foreground">+{ws.projects.length - 6} more</li>
          ) : null}
        </ul>
        <Button type="button" className="w-full mt-auto" asChild>
          <Link to={href}>{openLabel}</Link>
        </Button>
      </CardContent>
    </Card>
  )
}

function PublicationTitleRow() {
  const { organizationId, organizationName, isOrgAdmin, checkAuth } = useAuth()
  const display = organizationName ?? "Workspaces"

  return (
    <InlineNameEditor
      value={display}
      canEdit={isOrgAdmin && organizationId != null}
      ariaLabel="Publication name"
      editAriaLabel="Edit publication name"
      saveAriaLabel="Save publication name"
      onSave={async (next) => {
        if (!organizationId) return
        await patchOrganization(organizationId, { name: next })
        await checkAuth()
      }}
    />
  )
}

export default function WorkspacesHomePage() {
  const { organizationId, isOrgAdmin } = useAuth()
  const [rows, setRows] = useState<WorkspaceWithProjects[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [newWsName, setNewWsName] = useState("")
  const [creatingWs, setCreatingWs] = useState(false)
  const [createWsError, setCreateWsError] = useState<string | null>(null)

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

  const openCreateWorkspace = () => {
    setNewWsName("")
    setCreateWsError(null)
    setCreateOpen(true)
  }

  const submitCreateWorkspace = async () => {
    if (organizationId == null) return
    const name = newWsName.trim()
    if (!name) {
      setCreateWsError("Enter a workspace name.")
      return
    }
    setCreateWsError(null)
    setCreatingWs(true)
    try {
      await createWorkspace(organizationId, { name })
      setCreateOpen(false)
      await load()
      window.dispatchEvent(new CustomEvent("agate:workspaces-changed"))
    } catch (e) {
      setCreateWsError(e instanceof Error ? e.message : "Could not create workspace")
    } finally {
      setCreatingWs(false)
    }
  }

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

  const workspaceCreateDialog = (
    <Dialog open={createOpen} onOpenChange={setCreateOpen}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>New workspace</DialogTitle>
          <DialogDescription>
            Workspaces group projects. You can add projects from the sidebar after creating one.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-2 py-2">
          <Label htmlFor="ws-name">Name</Label>
          <Input
            id="ws-name"
            value={newWsName}
            onChange={(e) => setNewWsName(e.target.value)}
            placeholder="e.g. Investigations"
            disabled={creatingWs}
            onKeyDown={(e) => {
              if (e.key === "Enter") void submitCreateWorkspace()
            }}
          />
          {createWsError ? (
            <p className="text-sm text-destructive">{createWsError}</p>
          ) : null}
        </div>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => setCreateOpen(false)}>
            Cancel
          </Button>
          <Button
            type="button"
            className="inline-flex items-center"
            disabled={creatingWs || !newWsName.trim()}
            onClick={() => void submitCreateWorkspace()}
          >
            {creatingWs ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
                Creating…
              </>
            ) : (
              "Create workspace"
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )

  const showAddWorkspace = Boolean(isOrgAdmin && organizationId != null)
  const canUseTemplates = hasWorkspaceAccess(rows, Boolean(isOrgAdmin))

  if (rows.length === 0) {
    return (
      <div className="space-y-6">
        <div className="space-y-2">
          <PublicationTitleRow />
          <p className="text-muted-foreground text-sm">
            You don&apos;t have access to any projects yet. Ask an organization admin to grant
            workspace access to use flows in Agate.
          </p>
          {canUseTemplates ? (
            <Button type="button" variant="outline" asChild>
              <Link to="/templates">Browse templates</Link>
            </Button>
          ) : null}
        </div>
        {showAddWorkspace ? (
          <div className="flex max-w-xl justify-center sm:justify-start">
            <AddPlusCta label="Add Workspace" onClick={openCreateWorkspace} />
          </div>
        ) : null}
        {workspaceCreateDialog}
      </div>
    )
  }

  const gridEntries = workspaceGridEntries(rows, showAddWorkspace)

  return (
    <div className="space-y-8">
      <div>
        <PublicationTitleRow />
        <p className="text-muted-foreground text-sm mt-1 max-w-2xl">
          Open a workspace to work with its projects. Switch workspaces anytime from this page or
          the sidebar.
        </p>
      </div>

      <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {gridEntries.map((entry) =>
          entry.kind === "workspace" ? (
            <li key={`${entry.ws.slug}-${entry.ws.id}`} className="flex h-full min-h-0 w-full">
              <WorkspaceHomeCard ws={entry.ws} canUseTemplates={canUseTemplates} />
            </li>
          ) : (
            <li key="__add_workspace__" className="flex h-full min-h-0 w-full">
              <AddPlusCta
                label="Add Workspace"
                onClick={openCreateWorkspace}
                className="h-full min-h-0 w-full flex-1"
              />
            </li>
          ),
        )}
      </ul>
      {workspaceCreateDialog}
    </div>
  )
}
