import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import TypedNameDeleteDialog from '@/components/TypedNameDeleteDialog'
import { useAppMessage } from '@/components/AppMessageProvider'
import { useAuth } from '@/lib/auth'
import {
  deleteProject,
  getProjectDeletePreview,
  type Project,
  type ProjectDeletePreview,
} from '@/lib/api'
import { listMyWorkspaces } from '@/lib/core-api'

export default function ProjectDeleteDangerZone({ project }: { project: Project }) {
  const navigate = useNavigate()
  const { isOrgAdmin } = useAuth()
  const { showError, showMessage } = useAppMessage()
  const [open, setOpen] = useState(false)
  const [preview, setPreview] = useState<ProjectDeletePreview | null>(null)
  const [confirmName, setConfirmName] = useState('')
  const [loading, setLoading] = useState(false)
  const [deleting, setDeleting] = useState(false)

  if (!isOrgAdmin || project.slug === 'general') {
    return null
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
      let destination = '/'
      try {
        const rows = await listMyWorkspaces()
        const ws = rows.find((row) => row.id === project.workspace_id)
        if (ws) {
          destination = `/workspace/${encodeURIComponent(ws.slug)}`
        }
      } catch {
        /* fall back to workspaces home */
      }
      navigate(destination, { replace: true })
    } catch (e) {
      showError(e instanceof Error ? e.message : 'Could not delete project.')
    } finally {
      setDeleting(false)
    }
  }

  return (
    <>
      <div className="space-y-3 pt-4 border-t border-border">
        <h4 className="text-base font-semibold text-destructive">Delete project</h4>
        <p className="text-sm text-muted-foreground max-w-2xl">
          Permanently remove this project, its flows, runs, articles, and API keys. Shared
          stylebook entries for your organization are kept. This cannot be undone.
        </p>
        <Card>
          <CardContent className="p-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm text-muted-foreground">
              Only organization admins can delete a project.
            </p>
            <Button type="button" variant="destructive" onClick={() => void openDialog()}>
              Delete project…
            </Button>
          </CardContent>
        </Card>
      </div>

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
        description="This cannot be undone. Type the project name exactly to confirm."
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
