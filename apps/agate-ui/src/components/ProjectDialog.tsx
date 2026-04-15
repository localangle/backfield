import { useCallback, useEffect, useState } from 'react'
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
  const [name, setName] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const [workspaces, setWorkspaces] = useState<WorkspaceWithProjects[]>([])
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState<string>('') // string for Select

  const isEditing = !!project
  const isDefaultProject = project?.slug === 'general'

  const loadWorkspaces = useCallback(async () => {
    try {
      const rows = await listMyWorkspaces()
      // Exclude synthetic grouping (e.g. _ungrouped).
      const real = rows.filter((w) => w.id > 0 && w.slug !== '_ungrouped')
      setWorkspaces(real)
      if (isEditing) return
      if (defaultWorkspaceId != null && defaultWorkspaceId > 0) {
        setSelectedWorkspaceId(String(defaultWorkspaceId))
        return
      }
      if (!selectedWorkspaceId) {
        const def = real.find((w) => w.slug === 'default') ?? real[0]
        if (def) setSelectedWorkspaceId(String(def.id))
      }
    } catch (e) {
      console.error(e)
      setWorkspaces([])
    }
  }, [defaultWorkspaceId, isEditing, selectedWorkspaceId])

  useEffect(() => {
    if (project) {
      setName(project.name)
    } else {
      setName('')
    }
    if (open && !project) {
      void loadWorkspaces()
    }
  }, [project, open, loadWorkspaces])

  const handleSave = async () => {
    if (!name.trim()) return

    try {
      setIsLoading(true)
      const widLocked =
        defaultWorkspaceId != null && defaultWorkspaceId > 0
          ? defaultWorkspaceId
          : null
      const widSelect =
        selectedWorkspaceId && workspaces.length > 0
          ? parseInt(selectedWorkspaceId, 10)
          : NaN
      const wid =
        widLocked ?? (Number.isFinite(widSelect) ? widSelect : null)
      await onSave({ name: name.trim(), workspace_id: wid })
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
    if (e.key === 'Enter' && !isLoading) {
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
          {!isEditing &&
          workspaces.length > 0 &&
          (defaultWorkspaceId == null || defaultWorkspaceId <= 0) ? (
            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="workspace" className="text-right">
                Workspace
              </Label>
              <div className="col-span-3">
                <Select value={selectedWorkspaceId} onValueChange={setSelectedWorkspaceId}>
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
            <Button
              onClick={handleSave}
              disabled={!name.trim() || isLoading || isDeleting}
            >
              {isLoading ? 'Saving...' : (isEditing ? 'Update' : 'Create')}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
