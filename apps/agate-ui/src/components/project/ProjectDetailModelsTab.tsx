import { useCallback, useEffect, useMemo, useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
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

/** Matches Integrations tab — project-specific credential saved for this model. */
function OverriddenBadge() {
  return (
    <Badge
      variant="outline"
      className="border-amber-300 bg-amber-50 text-amber-950 shadow-none dark:border-amber-700 dark:bg-amber-950/50 dark:text-amber-100"
    >
      Overridden
    </Badge>
  )
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
    const override = row.project_credential_override_configured ?? false
    return (
      <div
        key={row.id}
        className="space-y-3 border-b border-border pb-6 pt-6 first:pt-0 last:border-0 last:pb-0"
      >
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0 space-y-0.5">
            <div className="text-sm font-medium">{row.name}</div>
            <div className="truncate text-xs text-muted-foreground font-mono">
              {row.provider}/{row.provider_model_id}
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2 shrink-0">
            {override ? <OverriddenBadge /> : <Badge variant="success">Configured</Badge>}
          </div>
        </div>
        <p className="text-xs text-muted-foreground">
          {override
            ? 'This project uses its own provider key for this model.'
            : 'This project uses your organization’s saved credential for this model.'}
        </p>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2">
            <Switch
              id={`model-${row.id}-enabled`}
              checked={row.project_enabled}
              disabled={busy}
              onCheckedChange={(v) => void handleToggleEnabled(row, v)}
              aria-label={row.project_enabled ? 'Turn off for this project' : 'Turn on for this project'}
            />
            <Label htmlFor={`model-${row.id}-enabled`} className="text-sm font-normal cursor-pointer">
              Available for this project
            </Label>
          </div>
          <div className="flex flex-wrap gap-2 shrink-0">
            <Button
              type="button"
              size="sm"
              className="bg-black text-white hover:bg-black/90"
              disabled={busy}
              onClick={() => openCredentialDialog(row)}
            >
              {override ? 'Update project key' : 'Use project key'}
            </Button>
            {override ? (
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={busy}
                onClick={() => void handleClearOverride(row)}
              >
                Remove
              </Button>
            ) : null}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="w-full min-w-0 space-y-6">
      <p className="text-sm text-muted-foreground">
        Turn models on or off to make them accessible to flows in this project.
      </p>

      <Card className="w-full">
        <CardHeader>
          <CardTitle className="text-base">Project models</CardTitle>
          <CardDescription>
            Organization admins manage the catalog. Use the switch to include or exclude a model here; optional keys
            override organization credentials for this project only.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-10">
          {loading ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
              Loading models…
            </div>
          ) : listError ? (
            <p className="text-sm text-muted-foreground">{listError}</p>
          ) : (
            <>
              <section className="space-y-4" aria-labelledby="models-available-heading">
                <h2 id="models-available-heading" className="text-sm font-semibold tracking-tight">
                  Available in this project
                </h2>
                {enabledRows.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No models enabled for this project.</p>
                ) : (
                  <div className="space-y-0">{enabledRows.map(renderRow)}</div>
                )}
              </section>

              <section className="space-y-4 border-t border-border pt-10" aria-labelledby="models-off-heading">
                <h2 id="models-off-heading" className="text-sm font-semibold tracking-tight">
                  Turned off for this project
                </h2>
                {disabledRows.length === 0 ? (
                  <p className="text-sm text-muted-foreground">None — every organization model is available.</p>
                ) : (
                  <div className="space-y-0">{disabledRows.map(renderRow)}</div>
                )}
              </section>
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
              className="bg-black text-white hover:bg-black/90"
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
    </div>
  )
}
