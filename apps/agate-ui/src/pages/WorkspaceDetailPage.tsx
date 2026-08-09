import { useCallback, useEffect, useState } from "react"
import { Link, useNavigate, useParams } from "react-router-dom"
import { FolderOpen, Loader2 } from "lucide-react"
import { AddPlusCta } from "@/components/AddPlusCta"
import { useAppMessage } from "@/components/AppMessageProvider"
import { InlineNameEditor } from "@/components/InlineNameEditor"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { PageBreadcrumbs } from "@/components/PageBreadcrumbs"
import ProjectDialog from "@/components/ProjectDialog"
import TypedNameDeleteDialog from "@/components/TypedNameDeleteDialog"
import { useAuth } from "@/lib/auth"
import { createProject, type ProjectCreate } from "@/lib/api"
import {
  deleteWorkspace,
  getWorkspaceDeletePreview,
  listMyWorkspaces,
  patchWorkspace,
  type ProjectSummary,
  type WorkspaceDeletePreview,
  type WorkspaceWithProjects,
} from "@/lib/core-api"

function WorkspaceTitleRow({
  workspace,
  organizationId,
  isOrgAdmin,
  onRenamed,
}: {
  workspace: WorkspaceWithProjects
  organizationId: number | null
  isOrgAdmin: boolean
  onRenamed: (next: WorkspaceWithProjects) => void
}) {
  return (
    <InlineNameEditor
      value={workspace.name}
      canEdit={isOrgAdmin && organizationId != null}
      ariaLabel="Workspace name"
      editAriaLabel="Edit workspace name"
      saveAriaLabel="Save workspace name"
      onSave={async (next) => {
        if (!organizationId) return
        const updated = await patchWorkspace(organizationId, workspace.id, { name: next })
        onRenamed(updated)
        window.dispatchEvent(new CustomEvent("agate:workspaces-changed"))
      }}
    />
  )
}

function ProjectHomeCard({ project }: { project: ProjectSummary }) {
  return (
    <Card className="h-full w-full flex flex-col hover:border-foreground/20 transition-colors">
      <CardHeader>
        <div className="flex items-start gap-2">
          <FolderOpen className="h-5 w-5 text-muted-foreground shrink-0 mt-0.5" />
          <div className="min-w-0">
            <CardTitle className="text-lg leading-snug">{project.name}</CardTitle>
          </div>
        </div>
      </CardHeader>
      <CardContent className="flex-1 flex flex-col gap-3 mt-auto">
        <Button type="button" className="w-full mt-auto" asChild>
          <Link to={`/project/${encodeURIComponent(project.slug)}`}>Open project</Link>
        </Button>
      </CardContent>
    </Card>
  )
}

export default function WorkspaceDetailPage() {
  const { workspaceSlug: workspaceSlugParam } = useParams<{ workspaceSlug: string }>()
  const navigate = useNavigate()
  const { organizationId, isOrgAdmin } = useAuth()
  const { showError, showMessage } = useAppMessage()
  const workspaceSlug =
    workspaceSlugParam != null ? decodeURIComponent(workspaceSlugParam) : ""

  const [workspace, setWorkspace] = useState<WorkspaceWithProjects | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [projectDialogOpen, setProjectDialogOpen] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [deletePreview, setDeletePreview] = useState<WorkspaceDeletePreview | null>(null)
  const [deleteConfirmName, setDeleteConfirmName] = useState("")
  const [deleteLoading, setDeleteLoading] = useState(false)
  const [deleting, setDeleting] = useState(false)

  const load = useCallback(async () => {
    setError(null)
    setLoading(true)
    try {
      const rows = await listMyWorkspaces()
      const w = rows.find(
        (x) => x.slug === workspaceSlug && x.id > 0 && x.slug !== "_ungrouped",
      )
      setWorkspace(w ?? null)
    } catch (e) {
      console.error(e)
      setError(e instanceof Error ? e.message : "Failed to load workspace")
      setWorkspace(null)
    } finally {
      setLoading(false)
    }
  }, [workspaceSlug])

  useEffect(() => {
    if (workspaceSlug === "_ungrouped" || workspaceSlug === "") {
      navigate("/", { replace: true })
      return
    }
    void load()
  }, [load, navigate, workspaceSlug])

  const handleCreateProject = async (data: ProjectCreate) => {
    await createProject(data)
    await load()
    window.dispatchEvent(new CustomEvent("agate:projects-changed"))
    window.dispatchEvent(new CustomEvent("agate:workspaces-changed"))
    setProjectDialogOpen(false)
  }

  const openDeleteDialog = async () => {
    if (!organizationId || !workspace) return
    setDeleteConfirmName("")
    setDeletePreview(null)
    setDeleteOpen(true)
    setDeleteLoading(true)
    try {
      setDeletePreview(await getWorkspaceDeletePreview(organizationId, workspace.id))
    } catch (e) {
      setDeleteOpen(false)
      showError(e instanceof Error ? e.message : "Could not load delete details.")
    } finally {
      setDeleteLoading(false)
    }
  }

  const handleDeleteWorkspace = async () => {
    if (!organizationId || !workspace || !deletePreview) return
    if (deleteConfirmName.trim() !== workspace.name.trim()) {
      showError("The name you typed does not match this workspace.")
      return
    }
    try {
      setDeleting(true)
      await deleteWorkspace(organizationId, workspace.id, deleteConfirmName.trim())
      showMessage("Workspace deleted.", { title: "Done" })
      window.dispatchEvent(new CustomEvent("agate:projects-changed"))
      window.dispatchEvent(new CustomEvent("agate:workspaces-changed"))
      navigate("/", { replace: true })
    } catch (e) {
      showError(e instanceof Error ? e.message : "Could not delete workspace.")
    } finally {
      setDeleting(false)
    }
  }

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[40vh] gap-3">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        <p className="text-sm text-muted-foreground">Loading workspace…</p>
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

  if (!workspace) {
    return (
      <div className="space-y-4 max-w-lg">
        <p className="text-muted-foreground text-sm">
          This workspace was not found or you don&apos;t have access.
        </p>
        <Button type="button" variant="outline" asChild>
          <Link to="/">Back to workspaces</Link>
        </Button>
      </div>
    )
  }

  const projects = [...workspace.projects].sort((a, b) => a.slug.localeCompare(b.slug))

  return (
    <div className="space-y-8">
      <div className="space-y-2">
        <PageBreadcrumbs items={[{ label: "Workspaces", to: "/" }, { label: workspace.name }]} />
        <WorkspaceTitleRow
          workspace={workspace}
          organizationId={organizationId}
          isOrgAdmin={isOrgAdmin}
          onRenamed={setWorkspace}
        />
        <p className="text-muted-foreground text-sm mt-1 max-w-2xl">
          Open a project to edit flows and runs, or add a new project to this workspace.
        </p>
      </div>

      <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {projects.map((p) => (
          <li key={p.id} className="flex h-full min-h-0 w-full">
            <ProjectHomeCard project={p} />
          </li>
        ))}
        <li key="__add_project__" className="flex h-full min-h-0 w-full">
          <AddPlusCta
            label="Add Project"
            onClick={() => setProjectDialogOpen(true)}
            className="h-full min-h-0 w-full flex-1"
          />
        </li>
      </ul>

      <ProjectDialog
        open={projectDialogOpen}
        onOpenChange={setProjectDialogOpen}
        project={null}
        onSave={handleCreateProject}
        defaultWorkspaceId={workspace.id}
      />

      {isOrgAdmin && organizationId != null ? (
        <div className="space-y-3 pt-4 border-t border-border">
          <h2 className="text-base font-semibold text-destructive">Delete workspace</h2>
          <p className="text-sm text-muted-foreground max-w-2xl">
            Permanently remove this workspace and every project inside it, including flows, runs,
            articles, and API keys. Shared catalog entries in your stylebooks are kept. This cannot
            be undone.
          </p>
          <Button type="button" variant="destructive" onClick={() => void openDeleteDialog()}>
            Delete workspace…
          </Button>
          <TypedNameDeleteDialog
            open={deleteOpen && (deleteLoading || deletePreview != null)}
            onOpenChange={(next) => {
              if (!next) {
                setDeleteOpen(false)
                setDeletePreview(null)
                setDeleteConfirmName("")
              }
            }}
            title="Delete workspace"
            description="This cannot be undone. Type the workspace name exactly to confirm."
            confirmLabel="Type the workspace name to confirm"
            confirmName={deleteConfirmName}
            onConfirmNameChange={setDeleteConfirmName}
            expectedName={workspace.name}
            loading={deleteLoading}
            deleting={deleting}
            deleteButtonLabel="Delete workspace"
            onConfirm={() => void handleDeleteWorkspace()}
          >
            {deletePreview ? (
              <p>
                <span className="font-medium">{deletePreview.name}</span> will remove{" "}
                <span className="font-medium">{deletePreview.project_count}</span>{" "}
                {deletePreview.project_count === 1 ? "project" : "projects"},{" "}
                <span className="font-medium">{deletePreview.flow_count}</span>{" "}
                {deletePreview.flow_count === 1 ? "flow" : "flows"},{" "}
                <span className="font-medium">{deletePreview.article_count}</span>{" "}
                {deletePreview.article_count === 1 ? "article" : "articles"}, and{" "}
                <span className="font-medium">{deletePreview.api_credential_count}</span> API{" "}
                {deletePreview.api_credential_count === 1 ? "key" : "keys"}.
              </p>
            ) : null}
          </TypedNameDeleteDialog>
        </div>
      ) : null}
    </div>
  )
}
