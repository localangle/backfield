import { useState } from 'react'
import { Button } from '@/components/ui/button'
import TypedNameDeleteDialog from '@/components/TypedNameDeleteDialog'
import { useAppMessage } from '@/components/AppMessageProvider'
import { useAuth } from '@/lib/auth'
import { cn } from '@/lib/utils'
import {
  deleteWorkspace,
  getWorkspaceDeletePreview,
  type WorkspaceDeletePreview,
  type WorkspaceWithProjects,
} from '@/lib/core-api'

export default function WorkspaceDeleteButton({
  workspace,
  onDeleted,
  className,
}: {
  workspace: WorkspaceWithProjects
  onDeleted?: () => void
  className?: string
}) {
  const { organizationId, isOrgAdmin } = useAuth()
  const { showError, showMessage } = useAppMessage()
  const [open, setOpen] = useState(false)
  const [preview, setPreview] = useState<WorkspaceDeletePreview | null>(null)
  const [confirmName, setConfirmName] = useState('')
  const [loading, setLoading] = useState(false)
  const [deleting, setDeleting] = useState(false)

  const isRealWorkspace = workspace.id > 0 && workspace.slug !== '_ungrouped'
  if (!isOrgAdmin || organizationId == null || !isRealWorkspace) {
    return null
  }

  const containsDefaultProject = workspace.projects.some((p) => p.slug === 'general')
  if (containsDefaultProject) {
    return (
      <p
        className={cn(
          'flex h-9 w-full items-center justify-center rounded-md border border-dashed border-border px-3 text-center text-xs text-muted-foreground',
          className,
        )}
        title="This workspace holds the default project and cannot be deleted."
      >
        Contains default project — can&apos;t be deleted
      </p>
    )
  }

  const openDialog = async () => {
    setConfirmName('')
    setPreview(null)
    setOpen(true)
    setLoading(true)
    try {
      setPreview(await getWorkspaceDeletePreview(organizationId, workspace.id))
    } catch (e) {
      setOpen(false)
      showError(e instanceof Error ? e.message : 'Could not load delete details.')
    } finally {
      setLoading(false)
    }
  }

  const onDelete = async () => {
    if (!preview) return
    if (confirmName.trim() !== workspace.name.trim()) {
      showError('The name you typed does not match this workspace.')
      return
    }
    try {
      setDeleting(true)
      await deleteWorkspace(organizationId, workspace.id, confirmName.trim())
      showMessage('Workspace deleted.', { title: 'Done' })
      window.dispatchEvent(new CustomEvent('agate:projects-changed'))
      window.dispatchEvent(new CustomEvent('agate:workspaces-changed'))
      setOpen(false)
      onDeleted?.()
    } catch (e) {
      showError(e instanceof Error ? e.message : 'Could not delete workspace.')
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
        title="Delete workspace"
        description="This permanently removes the workspace and every project inside it, including flows, runs, articles, and API keys. Shared Stylebook entries are kept. Type the workspace name exactly to confirm."
        confirmLabel="Type the workspace name to confirm"
        confirmName={confirmName}
        onConfirmNameChange={setConfirmName}
        expectedName={workspace.name}
        loading={loading}
        deleting={deleting}
        deleteButtonLabel="Delete workspace"
        onConfirm={() => void onDelete()}
      >
        {preview ? (
          <p>
            <span className="font-medium">{preview.name}</span> will remove{' '}
            <span className="font-medium">{preview.project_count}</span>{' '}
            {preview.project_count === 1 ? 'project' : 'projects'},{' '}
            <span className="font-medium">{preview.flow_count}</span>{' '}
            {preview.flow_count === 1 ? 'flow' : 'flows'},{' '}
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
