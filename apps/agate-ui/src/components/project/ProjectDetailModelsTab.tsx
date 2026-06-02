import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
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
  fetchProjectAiModelDefaults,
  fetchProjectEffectiveAiModels,
  putProjectAiModelAvailability,
  putProjectAiModelCredentialOverride,
  putProjectAiModelDefaultRole,
  type ProjectEffectiveAiModelRow,
} from '@/lib/core-api'
import {
  modelKindLabel,
  normalizeModelKind,
  SEMANTIC_EMBEDDING_DEFAULT_ROLE,
} from '@/lib/ai-model-catalog-ui'
import { partitionProjectModelsByKind } from '@/lib/project-models-ui'
import { Loader2 } from 'lucide-react'

function isAzureStyleModel(row: ProjectEffectiveAiModelRow): boolean {
  const p = row.provider?.toLowerCase() ?? ''
  const lm = row.litellm_model?.toLowerCase() ?? ''
  return p === 'azure' || lm.startsWith('azure/')
}

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
  const [semanticDefaultModelId, setSemanticDefaultModelId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [listError, setListError] = useState<string | null>(null)
  const [busyModelId, setBusyModelId] = useState<string | null>(null)
  const autoDefaultInFlight = useRef(false)

  const [credentialDialog, setCredentialDialog] = useState<ProjectEffectiveAiModelRow | null>(null)
  const [credentialKey, setCredentialKey] = useState('')
  const [credentialBase, setCredentialBase] = useState('')
  const [credentialSaving, setCredentialSaving] = useState(false)

  const partitioned = useMemo(() => partitionProjectModelsByKind(rows), [rows])
  const enabledEmbeddingIds = useMemo(
    () => partitioned.embedding.enabled.map((r) => r.id),
    [partitioned.embedding.enabled],
  )
  const soleEnabledEmbeddingId =
    enabledEmbeddingIds.length === 1 ? enabledEmbeddingIds[0] : null

  const reload = useCallback(async () => {
    try {
      setListError(null)
      setLoading(true)
      const [data, defaults] = await Promise.all([
        fetchProjectEffectiveAiModels(projectId, undefined, { includeDisabled: true }),
        fetchProjectAiModelDefaults(projectId),
      ])
      setRows(data)
      const semantic = defaults.find((d) => d.role === SEMANTIC_EMBEDDING_DEFAULT_ROLE)
      setSemanticDefaultModelId(semantic?.model_config_id ?? null)
    } catch (e) {
      console.error(e)
      setRows([])
      setSemanticDefaultModelId(null)
      setListError('Could not load models for this project.')
    } finally {
      setLoading(false)
    }
  }, [projectId])

  useEffect(() => {
    void reload()
  }, [reload])

  const setSemanticDefault = useCallback(
    async (modelConfigId: string) => {
      try {
        setBusyModelId(modelConfigId)
        await putProjectAiModelDefaultRole(
          projectId,
          SEMANTIC_EMBEDDING_DEFAULT_ROLE,
          modelConfigId,
        )
        setSemanticDefaultModelId(modelConfigId)
      } catch (e) {
        console.error(e)
        showError('We could not set the semantic search default. Try again.')
      } finally {
        setBusyModelId(null)
      }
    },
    [projectId, showError],
  )

  const maybeAutoAssignSoleEmbeddingDefault = useCallback(
    async (enabledEmbeddings: ProjectEffectiveAiModelRow[], currentDefaultId: string | null) => {
      if (enabledEmbeddings.length !== 1) return
      const soleId = enabledEmbeddings[0].id
      if (!soleId || soleId === currentDefaultId) return
      if (autoDefaultInFlight.current) return
      autoDefaultInFlight.current = true
      try {
        await putProjectAiModelDefaultRole(
          projectId,
          SEMANTIC_EMBEDDING_DEFAULT_ROLE,
          soleId,
        )
        setSemanticDefaultModelId(soleId)
      } catch (e) {
        console.error(e)
      } finally {
        autoDefaultInFlight.current = false
      }
    },
    [projectId],
  )

  useEffect(() => {
    if (loading) return
    void maybeAutoAssignSoleEmbeddingDefault(
      partitioned.embedding.enabled,
      semanticDefaultModelId,
    )
  }, [
    loading,
    partitioned.embedding.enabled,
    semanticDefaultModelId,
    maybeAutoAssignSoleEmbeddingDefault,
  ])

  const setBusy = (id: string | null) => setBusyModelId(id)

  const handleToggleEnabled = async (row: ProjectEffectiveAiModelRow, next: boolean) => {
    try {
      setBusy(row.id)
      const updated = await putProjectAiModelAvailability(projectId, row.id, next)
      const nextRows = rows.map((r) => (r.id === updated.id ? updated : r))
      setRows(nextRows)
      const enabledEmbeddings = nextRows.filter(
        (r) =>
          r.status === 'active' &&
          r.project_enabled &&
          normalizeModelKind(r.model_kind) === 'embedding',
      )
      await maybeAutoAssignSoleEmbeddingDefault(
        enabledEmbeddings,
        semanticDefaultModelId,
      )
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

  const renderModelRow = (
    row: ProjectEffectiveAiModelRow,
    options?: { showSemanticDefaultToggle?: boolean },
  ) => {
    const busy = busyModelId === row.id
    const override = row.project_credential_override_configured ?? false
    const isDefault = semanticDefaultModelId === row.id
    const lockDefaultOn =
      options?.showSemanticDefaultToggle === true &&
      soleEnabledEmbeddingId === row.id &&
      isDefault

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
            <Badge variant="outline">{modelKindLabel(normalizeModelKind(row.model_kind))}</Badge>
            {isDefault && options?.showSemanticDefaultToggle ? (
              <Badge variant="secondary">Semantic search default</Badge>
            ) : null}
            {override ? <OverriddenBadge /> : <Badge variant="success">Configured</Badge>}
          </div>
        </div>
        <p className="text-xs text-muted-foreground">
          {override
            ? 'This project uses its own provider key for this model.'
            : 'This project uses your organization’s saved credential for this model.'}
        </p>
        {options?.showSemanticDefaultToggle && row.project_enabled ? (
          <div className="flex items-center gap-2 rounded-md border border-border/60 bg-muted/20 px-3 py-2">
            <Switch
              id={`model-${row.id}-semantic-default`}
              checked={isDefault}
              disabled={busy || lockDefaultOn}
              onCheckedChange={(checked) => {
                if (checked) void setSemanticDefault(row.id)
              }}
              aria-label={
                isDefault
                  ? 'Default embedding model for semantic search'
                  : 'Set as default embedding model for semantic search'
              }
            />
            <Label
              htmlFor={`model-${row.id}-semantic-default`}
              className="text-sm font-normal cursor-pointer"
            >
              Default for semantic search
            </Label>
            {lockDefaultOn ? (
              <span className="text-xs text-muted-foreground">(only embedding model enabled)</span>
            ) : null}
          </div>
        ) : null}
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

  const renderKindSection = (
    title: string,
    description: string,
    enabled: ProjectEffectiveAiModelRow[],
    disabled: ProjectEffectiveAiModelRow[],
    options?: { showSemanticDefaultToggle?: boolean },
  ) => (
    <section className="space-y-4" aria-labelledby={`${title}-heading`}>
      <div className="space-y-1">
        <h2 id={`${title}-heading`} className="text-sm font-semibold tracking-tight">
          {title}
        </h2>
        <p className="text-sm text-muted-foreground">{description}</p>
      </div>
      <div className="space-y-4">
        <div className="space-y-0">
          <h3 className="text-xs font-medium uppercase tracking-wide text-muted-foreground mb-2">
            Available in this project
          </h3>
          {enabled.length === 0 ? (
            <p className="text-sm text-muted-foreground">No models enabled in this section.</p>
          ) : (
            enabled.map((row) => renderModelRow(row, options))
          )}
        </div>
        <div className="space-y-0 border-t border-border pt-6">
          <h3 className="text-xs font-medium uppercase tracking-wide text-muted-foreground mb-2">
            Turned off for this project
          </h3>
          {disabled.length === 0 ? (
            <p className="text-sm text-muted-foreground">None.</p>
          ) : (
            disabled.map((row) => renderModelRow(row, options))
          )}
        </div>
      </div>
    </section>
  )

  const hasGenerative =
    partitioned.generative.enabled.length > 0 || partitioned.generative.disabled.length > 0
  const hasEmbedding =
    partitioned.embedding.enabled.length > 0 || partitioned.embedding.disabled.length > 0

  return (
    <div className="w-full min-w-0 space-y-6">
      <p className="text-sm text-muted-foreground">
        Turn models on or off for this project. Embedding models power semantic search when Backfield
        Output has semantic search enabled.
      </p>

      <Card className="w-full">
        <CardHeader>
          <CardTitle className="text-base">Project models</CardTitle>
          <CardDescription>
            Organization admins manage the catalog under Settings → Models. Enable models here and
            choose which embedding model is the project default for semantic search.
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
          ) : !hasGenerative && !hasEmbedding ? (
            <p className="text-sm text-muted-foreground">
              No models in your organization catalog yet. Ask an administrator to add models under
              Settings → Models.
            </p>
          ) : (
            <>
              {hasGenerative
                ? renderKindSection(
                    'Generative',
                    'Language and vision models used in flow nodes such as extraction and geocoding.',
                    partitioned.generative.enabled,
                    partitioned.generative.disabled,
                  )
                : null}
              {hasGenerative && hasEmbedding ? (
                <div className="border-t border-border" />
              ) : null}
              {hasEmbedding
                ? renderKindSection(
                    'Embeddings',
                    'Vector models for semantic search across saved mentions. One enabled model is used automatically when it is the only choice.',
                    partitioned.embedding.enabled,
                    partitioned.embedding.disabled,
                    { showSemanticDefaultToggle: true },
                  )
                : null}
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
              Only flows that run in this project will use this key. It does not change organization
              settings.
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
