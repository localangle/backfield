import { useState } from 'react'
import { Button } from '@/components/ui/button'
import TypedNameDeleteDialog from '@/components/TypedNameDeleteDialog'
import { useAppMessage } from '@/components/AppMessageProvider'
import { useAuth } from '@/lib/auth'
import { cn } from '@/lib/utils'
import {
  deleteProject,
  getProjectDeletePreview,
  type ProjectDeletePreview,
} from '@/lib/api'

type ProjectDeleteTarget = {
  id: number
  name: string
  slug: string
}

export default function ProjectDeleteButton({
  project,
  onDeleted,
  className,
}: {
  project: ProjectDeleteTarget
  onDeleted?: () => void
  className?: string
}) {
  const { isOrgAdmin } = useAuth()
  const { showError, showMessage } = useAppMessage()
  const [open, setOpen] = useState(false)
  const [preview, setPreview] = useState<ProjectDeletePreview | null>(null)
  const [confirmName, setConfirmName] = useState('')
  const [loading, setLoading] = useState(false)
  const [deleting, setDeleting] = useState(false)

  if (!isOrgAdmin) {
    return null
  }

  if (project.slug === 'general') {
    return (
      <p
        className={cn(
          'flex h-9 w-full items-center justify-center rounded-md border border-dashed border-border px-3 text-center text-xs text-muted-foreground',
          className,
        )}
        title="General is the default project for this workspace and cannot be deleted."
      >
        Default project — can&apos;t be deleted
      </p>
    )
  }

  const openDialog = async () => {
    setConfirmName('')
    setPreview(null)
    setOpen(true)
    setLoading(true)
    try {
      setPreview(await getProjectDeletePreview(project.id))
    } catch (e) {
      setOpen(false)
      showError(e instanceof Error ? e.message : 'Could not load delete details.')
    } finally {
      setLoading(false)
    }
  }

  const onDelete = async () => {
    if (!preview) return
    if (confirmName.trim() !== project.name.trim()) {
      showError('The name you typed does not match this project.')
      return
    }
    try {
      setDeleting(true)
      await deleteProject(project.id, confirmName.trim())
      showMessage('Project deleted.', { title: 'Done' })
      window.dispatchEvent(new CustomEvent('agate:projects-changed'))
      window.dispatchEvent(new CustomEvent('agate:workspaces-changed'))
      setOpen(false)
      onDeleted?.()
    } catch (e) {
      showError(e instanceof Error ? e.message : 'Could not delete project.')
    } finally {
      setDeleting(false)
    }
  }

  return (
    <>
      <Button
        type="button"
        variant="outline"
        className={className}
        onClick={() => void openDialog()}
      >
        Delete
      </Button>
      <TypedNameDeleteDialog
        open={open && (loading || preview != null)}
        onOpenChange={(next) => {
          if (!next) {
            setOpen(false)
            setPreview(null)
            setConfirmName('')
          }
        }}
        title="Delete project"
        description="This permanently removes the project, its flows, runs, articles, and API keys. Shared Stylebook entries for your organization are kept. Type the project name exactly to confirm."
        confirmLabel="Type the project name to confirm"
        confirmName={confirmName}
        onConfirmNameChange={setConfirmName}
        expectedName={project.name}
        loading={loading}
        deleting={deleting}
        deleteButtonLabel="Delete project"
        onConfirm={() => void onDelete()}
      >
        {preview ? (
          <p>
            <span className="font-medium">{preview.name}</span> will remove{' '}
            <span className="font-medium">{preview.flow_count}</span>{' '}
            {preview.flow_count === 1 ? 'flow' : 'flows'},{' '}
            <span className="font-medium">{preview.processed_item_count}</span> processed{' '}
            {preview.processed_item_count === 1 ? 'item' : 'items'},{' '}
            <span className="font-medium">{preview.article_count}</span>{' '}
            {preview.article_count === 1 ? 'article' : 'articles'}, and{' '}
            <span className="font-medium">{preview.api_credential_count}</span> API{' '}
            {preview.api_credential_count === 1 ? 'key' : 'keys'}.
          </p>
        ) : null}
      </TypedNameDeleteDialog>
    </>
  )
}
