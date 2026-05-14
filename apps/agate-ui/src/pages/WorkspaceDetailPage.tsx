import { useCallback, useEffect, useRef, useState } from "react"
import { Link, useNavigate, useParams } from "react-router-dom"
import { Check, FolderOpen, Loader2, Pencil, X } from "lucide-react"
import { AddPlusCta } from "@/components/AddPlusCta"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { PageBreadcrumbs } from "@/components/PageBreadcrumbs"
import ProjectDialog from "@/components/ProjectDialog"
import { useAuth } from "@/lib/auth"
import { createProject, type ProjectCreate } from "@/lib/api"
import {
  listMyWorkspaces,
  patchWorkspace,
  type ProjectSummary,
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
  const display = workspace.name
  const [editingName, setEditingName] = useState(false)
  const [nameDraft, setNameDraft] = useState(display)
  const [savingName, setSavingName] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!editingName) setNameDraft(display)
  }, [display, editingName])

  useEffect(() => {
    if (editingName) inputRef.current?.focus()
  }, [editingName])

  const cancelNameEdit = () => {
    setNameDraft(display)
    setEditingName(false)
  }

  const saveName = async () => {
    if (!organizationId) return
    const next = nameDraft.trim()
    if (!next || next === display) {
      cancelNameEdit()
      return
    }
    try {
      setSavingName(true)
      const updated = await patchWorkspace(organizationId, workspace.id, { name: next })
      setEditingName(false)
      onRenamed(updated)
      window.dispatchEvent(new CustomEvent("agate:workspaces-changed"))
    } catch (e) {
      console.error(e)
    } finally {
      setSavingName(false)
    }
  }

  if (!isOrgAdmin || organizationId == null) {
    return <h1 className="text-2xl font-semibold tracking-tight">{display}</h1>
  }

  if (editingName) {
    return (
      <div className="flex w-full min-w-0 max-w-full flex-nowrap items-center gap-2">
        <Input
          ref={inputRef}
          value={nameDraft}
          onChange={(e) => setNameDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") void saveName()
            if (e.key === "Escape") cancelNameEdit()
          }}
          disabled={savingName}
          className="min-w-0 flex-1 max-w-xl text-2xl font-semibold h-auto py-2 px-3 tracking-tight"
          aria-label="Workspace name"
        />
        <Button
          type="button"
          size="icon"
          variant="default"
          className="shrink-0"
          disabled={savingName || !nameDraft.trim()}
          onClick={() => void saveName()}
          aria-label="Save workspace name"
        >
          <Check className="h-4 w-4" />
        </Button>
        <Button
          type="button"
          size="icon"
          variant="outline"
          className="shrink-0"
          disabled={savingName}
          onClick={cancelNameEdit}
          aria-label="Cancel"
        >
          <X className="h-4 w-4" />
        </Button>
      </div>
    )
  }

  return (
    <div className="inline-flex max-w-full min-h-[2.5rem] items-center gap-2">
      <h1 className="inline-block min-w-0 max-w-[min(100%,42rem)] truncate text-2xl font-semibold tracking-tight">
        {display}
      </h1>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="shrink-0 text-muted-foreground hover:text-foreground"
        onClick={() => {
          setNameDraft(display)
          setEditingName(true)
        }}
        aria-label="Edit workspace name"
      >
        <Pencil className="h-5 w-5" />
      </Button>
    </div>
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
  const workspaceSlug =
    workspaceSlugParam != null ? decodeURIComponent(workspaceSlugParam) : ""

  const [workspace, setWorkspace] = useState<WorkspaceWithProjects | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [projectDialogOpen, setProjectDialogOpen] = useState(false)

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
    </div>
  )
}
