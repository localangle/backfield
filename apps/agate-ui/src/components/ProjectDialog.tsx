import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import type { Project, ProjectCreate } from '@/lib/api'

interface ProjectDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  project?: Project | null
  onSave: (data: ProjectCreate) => Promise<void>
  onDelete?: (project: Project) => Promise<void>
}

export default function ProjectDialog({
  open,
  onOpenChange,
  project,
  onSave,
  onDelete
}: ProjectDialogProps) {
  const [name, setName] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)

  const isEditing = !!project
  const isDefaultProject = project?.slug === 'general'

  useEffect(() => {
    if (project) {
      setName(project.name)
    } else {
      setName('')
    }
  }, [project, open])

  const handleSave = async () => {
    if (!name.trim()) return

    try {
      setIsLoading(true)
      await onSave({ name: name.trim() })
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
