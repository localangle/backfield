import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import type { Project, ProjectCreate } from '@/lib/api'
import { listMyWorkspaces, type WorkspaceWithProjects } from '@/lib/core-api'
import { listStylebookCatalogs, type StylebookCatalogRow } from '@/lib/stylebook-org-api'
import { useAuth } from '@/lib/auth'
import {
  resolveStylebookSelection,
  shouldOfferStylebookChoice,
  stylebookIdForCreate,
  type StylebookSelectionInput,
} from '@/lib/projectStylebookChoice'

interface ProjectDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  project?: Project | null
  onSave: (data: ProjectCreate) => Promise<void>
  onDelete?: (project: Project) => Promise<void>
  /** When creating, lock new projects to this workspace (hides workspace selector). */
  defaultWorkspaceId?: number | null
}

export default function ProjectDialog({
  open,
  onOpenChange,
  project,
  onSave,
  onDelete,
  defaultWorkspaceId = null,
}: ProjectDialogProps) {
  const { organizationId } = useAuth()
  const [name, setName] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const [workspaces, setWorkspaces] = useState<WorkspaceWithProjects[]>([])
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState<string>('') // string for Select
  const [stylebooks, setStylebooks] = useState<StylebookCatalogRow[]>([])
  const [chosenStylebookId, setChosenStylebookId] = useState<number | null>(null)
  const [choicesLoading, setChoicesLoading] = useState(false)

  const isEditing = !!project
  const isDefaultProject = project?.slug === 'general'
  const lockedWorkspaceId =
    defaultWorkspaceId != null && defaultWorkspaceId > 0 ? defaultWorkspaceId : null

  useEffect(() => {
    setName(project ? project.name : '')
  }, [project, open])

  // Clear every choice as the dialog closes, so reopening never shows or submits a stale pick.
  useEffect(() => {
    if (open) return
    setWorkspaces([])
    setSelectedWorkspaceId('')
    setStylebooks([])
    setChosenStylebookId(null)
    setChoicesLoading(false)
  }, [open])

  useEffect(() => {
    if (!open || project) return
    let cancelled = false
    setChoicesLoading(true)

    const load = async () => {
      const [workspaceRows, stylebookRows] = await Promise.all([
        listMyWorkspaces().catch((e) => {
          console.error(e)
          return [] as WorkspaceWithProjects[]
        }),
        organizationId == null
          ? Promise.resolve([] as StylebookCatalogRow[])
          : listStylebookCatalogs(organizationId).catch((e) => {
              console.error(e)
              return [] as StylebookCatalogRow[]
            }),
      ])
      if (cancelled) return
      // Exclude synthetic grouping (e.g. _ungrouped).
      const real = workspaceRows.filter((w) => w.id > 0 && w.slug !== '_ungrouped')
      setWorkspaces(real)
      setStylebooks(stylebookRows)
      setChoicesLoading(false)
      if (lockedWorkspaceId != null) {
        setSelectedWorkspaceId(String(lockedWorkspaceId))
        return
      }
      const def = real.find((w) => w.slug === 'default') ?? real[0]
      setSelectedWorkspaceId(def ? String(def.id) : '')
    }

    void load()
    return () => {
      cancelled = true
    }
  }, [open, project, organizationId, lockedWorkspaceId])

  const parsedWorkspaceId = selectedWorkspaceId ? Number(selectedWorkspaceId) : Number.NaN
  const activeWorkspaceId =
    lockedWorkspaceId ?? (Number.isFinite(parsedWorkspaceId) ? parsedWorkspaceId : null)
  const stylebookSelection: StylebookSelectionInput = {
    stylebooks,
    workspaceStylebookId:
      workspaces.find((w) => w.id === activeWorkspaceId)?.stylebook_id ?? null,
    chosenStylebookId,
  }
  const showStylebookChoice = !isEditing && shouldOfferStylebookChoice(stylebooks)
  const selectedStylebookId = resolveStylebookSelection(stylebookSelection)
  const busy = isLoading || isDeleting || choicesLoading

  const handleSave = async () => {
    if (!name.trim()) return

    try {
      setIsLoading(true)
      if (activeWorkspaceId == null) return
      await onSave({
        name: name.trim(),
        workspace_id: activeWorkspaceId,
        stylebook_id: stylebookIdForCreate(stylebookSelection),
      })
      onOpenChange(false)
      setName('')
    } catch (error) {
      console.error('Failed to save project:', error)
    } finally {
      setIsLoading(false)
    }
  }

  const handleDelete = async () => {
    if (!project || isDefaultProject) return

    try {
      setIsDeleting(true)
      await onDelete?.(project)
      onOpenChange(false)
    } catch (error) {
      console.error('Failed to delete project:', error)
    } finally {
      setIsDeleting(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !busy) {
      handleSave()
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle>
            {isEditing ? 'Edit Project' : 'Create Project'}
          </DialogTitle>
          <DialogDescription>
            {isEditing 
              ? 'Update the project details below.'
              : 'Create a new project to organize your flows and runs.'
            }
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-4">
          <div className="grid grid-cols-4 items-center gap-4">
            <Label htmlFor="name" className="text-right">
              Name
            </Label>
            <Input
              id="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Project name"
              className="col-span-3"
              disabled={isLoading || isDeleting}
            />
          </div>
          {!isEditing && workspaces.length > 0 && lockedWorkspaceId == null ? (
            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="workspace" className="text-right">
                Workspace
              </Label>
              <div className="col-span-3">
                <Select
                  value={selectedWorkspaceId}
                  onValueChange={setSelectedWorkspaceId}
                  disabled={busy}
                >
                  <SelectTrigger id="workspace">
                    <SelectValue placeholder="Select a workspace" />
                  </SelectTrigger>
                  <SelectContent>
                    {workspaces.map((ws) => (
                      <SelectItem key={ws.id} value={String(ws.id)}>
                        {ws.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          ) : null}
          {showStylebookChoice ? (
            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="stylebook" className="text-right">
                Stylebook
              </Label>
              <div className="col-span-3">
                <Select
                  value={selectedStylebookId != null ? String(selectedStylebookId) : ''}
                  onValueChange={(value) => setChosenStylebookId(Number(value))}
                  disabled={busy}
                >
                  <SelectTrigger id="stylebook" aria-describedby="stylebook-help">
                    <SelectValue placeholder="Select a Stylebook" />
                  </SelectTrigger>
                  <SelectContent>
                    {stylebooks.map((sb) => (
                      <SelectItem key={sb.id} value={String(sb.id)}>
                        {sb.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p id="stylebook-help" className="mt-1 text-xs text-muted-foreground">
                  The project keeps this Stylebook after it is created.
                </p>
              </div>
            </div>
          ) : null}
        </div>

        <DialogFooter className="flex justify-between">
          <div>
            {isEditing && !isDefaultProject && onDelete && (
              <Button
                variant="destructive"
                onClick={handleDelete}
                disabled={isLoading || isDeleting}
              >
                {isDeleting ? 'Deleting...' : 'Delete'}
              </Button>
            )}
          </div>
          
          <div className="flex gap-2">
            <Button
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={isLoading || isDeleting}
            >
              Cancel
            </Button>
            <Button onClick={handleSave} disabled={!name.trim() || busy}>
              {isLoading
                ? 'Saving...'
                : choicesLoading
                  ? 'Loading...'
                  : isEditing
                    ? 'Update'
                    : 'Create'}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
