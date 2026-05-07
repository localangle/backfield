import { useCallback, useEffect, useMemo, useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { useAppMessage } from '@/components/AppMessageProvider'
import {
  deleteProjectAiModelCredentialOverride,
  fetchProjectEffectiveAiModels,
  putProjectAiModelAvailability,
  putProjectAiModelCredentialOverride,
  type ProjectEffectiveAiModelRow,
} from '@/lib/core-api'
import { Loader2 } from 'lucide-react'

function isAzureStyleModel(row: ProjectEffectiveAiModelRow): boolean {
  const p = row.provider?.toLowerCase() ?? ''
  const lm = row.litellm_model?.toLowerCase() ?? ''
  return p === 'azure' || lm.startsWith('azure/')
}

interface ProjectDetailModelsTabProps {
  projectId: number
}

export default function ProjectDetailModelsTab({ projectId }: ProjectDetailModelsTabProps) {
  const { showError, showConfirm, showMessage } = useAppMessage()
  const [rows, setRows] = useState<ProjectEffectiveAiModelRow[]>([])
  const [loading, setLoading] = useState(false)
  const [listError, setListError] = useState<string | null>(null)
  const [busyModelId, setBusyModelId] = useState<string | null>(null)

  const [credentialDialog, setCredentialDialog] = useState<ProjectEffectiveAiModelRow | null>(null)
  const [credentialKey, setCredentialKey] = useState('')
  const [credentialBase, setCredentialBase] = useState('')
  const [credentialSaving, setCredentialSaving] = useState(false)

  const reload = useCallback(async () => {
    try {
      setListError(null)
      setLoading(true)
      const data = await fetchProjectEffectiveAiModels(projectId, undefined, {
        includeDisabled: true,
      })
      setRows(data)
    } catch (e) {
      console.error(e)
      setRows([])
      setListError('Could not load models for this project.')
    } finally {
      setLoading(false)
    }
  }, [projectId])

  useEffect(() => {
    void reload()
  }, [reload])

  const enabledRows = useMemo(
    () => rows.filter((m) => m.status === 'active' && m.project_enabled),
    [rows],
  )
  const disabledRows = useMemo(
    () => rows.filter((m) => m.status === 'active' && !m.project_enabled),
    [rows],
  )

  const setBusy = (id: string | null) => setBusyModelId(id)

  const handleToggleEnabled = async (row: ProjectEffectiveAiModelRow, next: boolean) => {
    try {
      setBusy(row.id)
      const updated = await putProjectAiModelAvailability(projectId, row.id, next)
      setRows((prev) => prev.map((r) => (r.id === updated.id ? updated : r)))
    } catch (e) {
      console.error(e)
      showError('We could not update this model. Try again.')
    } finally {
      setBusy(null)
    }
  }

  const openCredentialDialog = (row: ProjectEffectiveAiModelRow) => {
    setCredentialDialog(row)
    setCredentialKey('')
    setCredentialBase('')
  }

  const submitCredentialOverride = async () => {
    const row = credentialDialog
    if (!row) return
    const key = credentialKey.trim()
    if (!key) {
      showMessage('Enter the provider key you want to use for this project.', {
        title: 'Missing key',
      })
      return
    }
    const base = credentialBase.trim()
    if (isAzureStyleModel(row) && !base) {
      showMessage('Azure OpenAI needs your resource endpoint URL as well as the key.', {
        title: 'Missing endpoint',
      })
      return
    }
    try {
      setCredentialSaving(true)
      const updated = await putProjectAiModelCredentialOverride(projectId, row.id, {
        api_key: key,
        api_base: base || null,
      })
      setRows((prev) => prev.map((r) => (r.id === updated.id ? updated : r)))
      setCredentialDialog(null)
      showMessage('Saved a key that applies only when flows run in this project.', {
        title: 'Saved',
      })
    } catch (e) {
      console.error(e)
      showError('We could not save this key. Check the key and endpoint, then try again.')
    } finally {
      setCredentialSaving(false)
    }
  }

  const handleClearOverride = async (row: ProjectEffectiveAiModelRow) => {
    const ok = await showConfirm(
      'Flows in this project will use your organization’s saved credential for this model again.',
      { title: 'Remove project key?', confirmLabel: 'Remove', destructive: true },
    )
    if (!ok) return
    try {
      setBusy(row.id)
      const updated = await deleteProjectAiModelCredentialOverride(projectId, row.id)
      setRows((prev) => prev.map((r) => (r.id === updated.id ? updated : r)))
      showMessage('This project now uses the organization credential for this model.', {
        title: 'Removed',
      })
    } catch (e) {
      console.error(e)
      showError('We could not remove the project key. Try again.')
    } finally {
      setBusy(null)
    }
  }

  const renderRow = (row: ProjectEffectiveAiModelRow) => {
    const busy = busyModelId === row.id
    return (
      <li
        key={row.id}
        className="rounded-md border border-border px-3 py-3 space-y-3"
      >
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-medium">{row.name}</div>
            <div className="truncate text-xs text-muted-foreground font-mono">
              {row.provider}/{row.provider_model_id}
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <Label htmlFor={`model-${row.id}-enabled`} className="text-xs text-muted-foreground sr-only">
              Enabled for this project
            </Label>
            <Switch
              id={`model-${row.id}-enabled`}
              checked={row.project_enabled}
              disabled={busy}
              onCheckedChange={(v) => void handleToggleEnabled(row, v)}
              aria-label={row.project_enabled ? 'Turn off for this project' : 'Turn on for this project'}
            />
          </div>
        </div>
        <div className="text-xs text-muted-foreground">
          {(row.project_credential_override_configured ?? false)
            ? 'This project uses its own provider key for this model.'
            : 'This project uses your organization’s saved credential for this model.'}
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={busy}
            onClick={() => openCredentialDialog(row)}
          >
            {(row.project_credential_override_configured ?? false) ? 'Update project key' : 'Use project key'}
          </Button>
          {(row.project_credential_override_configured ?? false) ? (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={busy}
              onClick={() => void handleClearOverride(row)}
            >
              Use organization key
            </Button>
          ) : null}
        </div>
      </li>
    )
  }

  return (
    <>
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground">
            Models for this project
          </CardTitle>
          <p className="text-sm text-muted-foreground pt-1">
            Turn models off for this project or paste a provider key that applies only here. Organization admins still
            manage which models exist for your organization.
          </p>
        </CardHeader>
        <CardContent className="space-y-6">
          {loading ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
              Loading models…
            </div>
          ) : listError ? (
            <p className="text-sm text-muted-foreground">{listError}</p>
          ) : (
            <>
              <div>
                <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">
                  Available in this project
                </h3>
                {enabledRows.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No models enabled for this project.</p>
                ) : (
                  <ul className="space-y-3">{enabledRows.map(renderRow)}</ul>
                )}
              </div>
              <div>
                <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">
                  Turned off for this project
                </h3>
                {disabledRows.length === 0 ? (
                  <p className="text-sm text-muted-foreground">None — every organization model is available.</p>
                ) : (
                  <ul className="space-y-3">{disabledRows.map(renderRow)}</ul>
                )}
              </div>
            </>
          )}
        </CardContent>
      </Card>

      <Dialog open={credentialDialog != null} onOpenChange={(o) => !o && setCredentialDialog(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Project key for {credentialDialog?.name ?? 'model'}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <p className="text-sm text-muted-foreground">
              Only flows that run in this project will use this key. It does not change organization settings.
            </p>
            <div className="space-y-1">
              <Label htmlFor="proj-model-key">Provider key</Label>
              <Input
                id="proj-model-key"
                type="password"
                autoComplete="off"
                value={credentialKey}
                onChange={(e) => setCredentialKey(e.target.value)}
                placeholder="Paste key"
              />
            </div>
            {credentialDialog && isAzureStyleModel(credentialDialog) ? (
              <div className="space-y-1">
                <Label htmlFor="proj-model-base">Resource endpoint URL</Label>
                <Input
                  id="proj-model-base"
                  type="url"
                  autoComplete="off"
                  value={credentialBase}
                  onChange={(e) => setCredentialBase(e.target.value)}
                  placeholder="https://…"
                />
              </div>
            ) : null}
          </div>
          <DialogFooter className="gap-2 sm:gap-0">
            <Button type="button" variant="outline" onClick={() => setCredentialDialog(null)}>
              Cancel
            </Button>
            <Button
              type="button"
              disabled={credentialSaving}
              onClick={() => void submitCredentialOverride()}
            >
              {credentialSaving ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Saving…
                </>
              ) : (
                'Save'
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
