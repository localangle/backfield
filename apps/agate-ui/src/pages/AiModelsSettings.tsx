import { useCallback, useEffect, useState, type Dispatch, type SetStateAction } from 'react'
import { useAppMessage } from '@/components/AppMessageProvider'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  createOrganizationAiModel,
  deleteOrganizationIntegrationSecret,
  fetchMe,
  listAiModelCuratedOptions,
  listAiProviderIntegrationCatalog,
  listOrganizationAiModels,
  patchOrganizationAiModel,
  putOrganizationIntegrationSecret,
  testOrganizationAiModelConnection,
  type AiModelConfigPatchInput,
  type AiModelConfigRow,
  type AiProviderCatalogEntry,
  type CuratedAiModelOption,
} from '@/lib/core-api'
import { Loader2, Plus } from 'lucide-react'

const CAP_KEYS = ['text', 'json', 'vision'] as const

const CAP_LABEL: Record<(typeof CAP_KEYS)[number], string> = {
  text: 'Text',
  json: 'Structured responses',
  vision: 'Image inputs',
}

function formatPriceField(v: unknown): string {
  if (v == null || v === '') return ''
  return typeof v === 'number' ? String(v) : String(v)
}

function normalizeCapabilityList(selected: Set<string>): string[] {
  return CAP_KEYS.filter((k) => selected.has(k))
}

function providerDisplayName(providerSlug: string): string {
  if (providerSlug === 'openai') return 'OpenAI'
  if (providerSlug === 'anthropic') return 'Anthropic'
  if (providerSlug === 'gemini') return 'Gemini'
  if (providerSlug === 'openrouter') return 'OpenRouter'
  if (providerSlug === 'azure') return 'Azure OpenAI'
  if (providerSlug === 'azure_endpoint') return 'Azure OpenAI endpoint'
  const u = providerSlug.replace(/_/g, ' ')
  return u.slice(0, 1).toUpperCase() + u.slice(1)
}

function credentialIsEndpointUrl(providerSlug: string): boolean {
  return providerSlug === 'azure_endpoint'
}

export default function AiModelsSettingsPage() {
  const { showConfirm, showError, showMessage } = useAppMessage()
  const [orgId, setOrgId] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [models, setModels] = useState<AiModelConfigRow[]>([])
  const [addOpen, setAddOpen] = useState(false)
  const [editRow, setEditRow] = useState<AiModelConfigRow | null>(null)
  const [testingId, setTestingId] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const [curatedOptions, setCuratedOptions] = useState<CuratedAiModelOption[]>([])
  const [addTab, setAddTab] = useState<'preset' | 'custom'>('preset')
  const [presetCuratedId, setPresetCuratedId] = useState<string>('')
  const [presetName, setPresetName] = useState('')
  const [presetCaps, setPresetCaps] = useState<Set<string>>(new Set())
  const [presetCurrency, setPresetCurrency] = useState('USD')
  const [presetPriceIn, setPresetPriceIn] = useState('')
  const [presetPriceOut, setPresetPriceOut] = useState('')
  const [presetPriceInAuto, setPresetPriceInAuto] = useState('')
  const [presetPriceOutAuto, setPresetPriceOutAuto] = useState('')

  const [customName, setCustomName] = useState('')
  const [customProvider, setCustomProvider] = useState('')
  const [customProviderModelId, setCustomProviderModelId] = useState('')
  const [customCaps, setCustomCaps] = useState<Set<string>>(new Set(['text', 'json']))
  const [customCurrency, setCustomCurrency] = useState('USD')
  const [customPriceIn, setCustomPriceIn] = useState('')
  const [customPriceOut, setCustomPriceOut] = useState('')

  const [editName, setEditName] = useState('')
  const [editStatus, setEditStatus] = useState<'active' | 'disabled'>('active')
  const [editCaps, setEditCaps] = useState<Set<string>>(new Set())
  const [editCurrency, setEditCurrency] = useState('USD')
  const [editPriceIn, setEditPriceIn] = useState('')
  const [editPriceOut, setEditPriceOut] = useState('')

  const [providerCatalog, setProviderCatalog] = useState<AiProviderCatalogEntry[]>([])
  const [providersError, setProvidersError] = useState<string | null>(null)
  const [credentialDialogEntry, setCredentialDialogEntry] = useState<AiProviderCatalogEntry | null>(
    null,
  )
  const [credentialValue, setCredentialValue] = useState('')
  const [credentialSaving, setCredentialSaving] = useState(false)

  const refreshOrgAiData = useCallback(async (oid: number) => {
    const settled = await Promise.allSettled([
      listOrganizationAiModels(oid),
      listAiProviderIntegrationCatalog(oid),
    ])
    const modelsResult = settled[0]
    const providersResult = settled[1]
    if (modelsResult.status === 'fulfilled') {
      setModels(modelsResult.value)
      setError(null)
    } else {
      setModels([])
      const r = modelsResult.reason
      setError(r instanceof Error ? r.message : 'Could not load catalog.')
    }
    if (providersResult.status === 'fulfilled') {
      setProviderCatalog(providersResult.value)
      setProvidersError(null)
    } else {
      setProviderCatalog([])
      const r = providersResult.reason
      setProvidersError(
        r instanceof Error ? r.message : 'Could not load provider credentials.',
      )
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      setError(null)
      setProvidersError(null)
      try {
        const me = await fetchMe()
        const oid = me.organization_id
        if (oid == null) {
          throw new Error('No organization on your session.')
        }
        if (cancelled) return
        setOrgId(oid)
        await refreshOrgAiData(oid)
      } catch (e: unknown) {
        if (!cancelled) {
          setModels([])
          setProviderCatalog([])
          setError(e instanceof Error ? e.message : 'Could not load this page.')
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [refreshOrgAiData])

  useEffect(() => {
    if (!addOpen || orgId == null) return
    let cancelled = false
    listAiModelCuratedOptions(orgId)
      .then((opts) => {
        if (!cancelled) {
          setCuratedOptions(opts)
          const first = opts[0]
          if (first) {
            setPresetCuratedId(first.curated_id)
            setPresetCaps(new Set(first.capabilities))
          }
        }
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          showError(e instanceof Error ? e.message : 'Could not load presets.')
        }
      })
    return () => {
      cancelled = true
    }
  }, [addOpen, orgId, showError])

  useEffect(() => {
    const opt = curatedOptions.find((o) => o.curated_id === presetCuratedId)
    if (opt) {
      setPresetCaps(new Set(opt.capabilities))
      if (presetCurrency.trim() === '' || presetCurrency.trim().toUpperCase() === 'USD') {
        const nextCur = (opt.currency ?? 'USD').trim().toUpperCase()
        if (nextCur) setPresetCurrency(nextCur)
      }
      const fmtTokenPrice = (v: unknown): string => {
        if (v === null || v === undefined) return ''
        const n = Number(v)
        if (!Number.isFinite(n)) return String(v)
        // Prevent scientific notation; keep enough precision for token pricing.
        const fixed = n.toLocaleString(undefined, {
          useGrouping: false,
          maximumFractionDigits: 18,
        })
        // Trim trailing zeros (and trailing '.' if needed).
        return fixed.replace(/(\.\d*?[1-9])0+$/g, '$1').replace(/\.0+$/g, '').replace(/\.$/g, '')
      }

      const nextIn = fmtTokenPrice(opt.input_token_price)
      const nextOut = fmtTokenPrice(opt.output_token_price)

      const canOverwriteIn =
        presetPriceIn.trim() === '' || presetPriceIn === presetPriceInAuto
      const canOverwriteOut =
        presetPriceOut.trim() === '' || presetPriceOut === presetPriceOutAuto

      if (canOverwriteIn) {
        setPresetPriceIn(nextIn)
        setPresetPriceInAuto(nextIn)
      }
      if (canOverwriteOut) {
        setPresetPriceOut(nextOut)
        setPresetPriceOutAuto(nextOut)
      }
    }
  }, [
    presetCuratedId,
    curatedOptions,
    presetCurrency,
    presetPriceIn,
    presetPriceOut,
    presetPriceInAuto,
    presetPriceOutAuto,
  ])

  function resetAddForm() {
    setAddTab('preset')
    setPresetName('')
    setPresetCurrency('USD')
    setPresetPriceIn('')
    setPresetPriceOut('')
    setPresetPriceInAuto('')
    setPresetPriceOutAuto('')
    setCustomName('')
    setCustomProvider('')
    setCustomProviderModelId('')
    setCustomCaps(new Set(['text', 'json']))
    setCustomCurrency('USD')
    setCustomPriceIn('')
    setCustomPriceOut('')
    const first = curatedOptions[0]
    if (first) {
      setPresetCuratedId(first.curated_id)
      setPresetCaps(new Set(first.capabilities))
    }
  }

  function openEdit(row: AiModelConfigRow) {
    setEditRow(row)
    setEditName(row.name)
    setEditStatus(row.status === 'disabled' ? 'disabled' : 'active')
    setEditCaps(new Set(row.capabilities))
    setEditCurrency(row.currency || 'USD')
    setEditPriceIn(formatPriceField(row.input_token_price))
    setEditPriceOut(formatPriceField(row.output_token_price))
  }

  function optionalPricePayload(
    inStr: string,
    outStr: string,
  ): Pick<AiModelConfigPatchInput, 'input_token_price' | 'output_token_price'> {
    const ti = inStr.trim()
    const to = outStr.trim()
    const out: Pick<AiModelConfigPatchInput, 'input_token_price' | 'output_token_price'> = {}
    if (ti === '') out.input_token_price = null
    else {
      const n = Number(ti)
      if (!Number.isFinite(n) || n < 0) throw new Error('Input usage price must be a valid number.')
      out.input_token_price = n
    }
    if (to === '') out.output_token_price = null
    else {
      const n = Number(to)
      if (!Number.isFinite(n) || n < 0) throw new Error('Output usage price must be a valid number.')
      out.output_token_price = n
    }
    return out
  }

  async function handleAddSubmit() {
    if (orgId == null) return
    setSubmitting(true)
    try {
      if (addTab === 'preset') {
        if (!presetCuratedId) {
          showError('Choose a preset model.')
          return
        }
        const caps = normalizeCapabilityList(presetCaps)
        if (caps.length === 0) {
          showError('Select at least one capability.')
          return
        }
        const prices =
          presetPriceIn.trim() === '' && presetPriceOut.trim() === ''
            ? {}
            : optionalPricePayload(presetPriceIn, presetPriceOut)
        await createOrganizationAiModel(orgId, {
          curated_id: presetCuratedId,
          name: presetName.trim() || undefined,
          capabilities: caps,
          currency: presetCurrency.trim().toUpperCase() || 'USD',
          ...prices,
        })
      } else {
        if (!customName.trim()) {
          showError('Display name is required.')
          return
        }
        if (!customProvider.trim() || !customProviderModelId.trim()) {
          showError('Provider and model id are required.')
          return
        }
        const caps = normalizeCapabilityList(customCaps)
        if (caps.length === 0) {
          showError('Select at least one capability.')
          return
        }
        const prices =
          customPriceIn.trim() === '' && customPriceOut.trim() === ''
            ? {}
            : optionalPricePayload(customPriceIn, customPriceOut)
        await createOrganizationAiModel(orgId, {
          name: customName.trim(),
          provider: customProvider.trim().toLowerCase(),
          provider_model_id: customProviderModelId.trim(),
          capabilities: caps,
          currency: customCurrency.trim().toUpperCase() || 'USD',
          ...prices,
        })
      }
      await refreshOrgAiData(orgId)
      setAddOpen(false)
      resetAddForm()
      showMessage('Model added to your organization catalog.')
    } catch (e: unknown) {
      showError(e instanceof Error ? e.message : 'Could not add model.')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleEditSave() {
    if (orgId == null || editRow == null) return
    setSubmitting(true)
    try {
      const caps = normalizeCapabilityList(editCaps)
      if (caps.length === 0) {
        showError('Select at least one capability.')
        return
      }
      const prices = optionalPricePayload(editPriceIn, editPriceOut)
      await patchOrganizationAiModel(orgId, editRow.id, {
        name: editName.trim(),
        status: editStatus,
        capabilities: caps,
        currency: editCurrency.trim().toUpperCase(),
        ...prices,
      })
      await refreshOrgAiData(orgId)
      setEditRow(null)
      showMessage('Model updated.')
    } catch (e: unknown) {
      showError(e instanceof Error ? e.message : 'Could not update model.')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleTestConnection(row: AiModelConfigRow) {
    if (orgId == null) return
    setTestingId(row.id)
    try {
      await testOrganizationAiModelConnection(orgId, row.id)
      await refreshOrgAiData(orgId)
      showMessage('Connection test finished. Status updated for this model.')
    } catch (e: unknown) {
      showError(e instanceof Error ? e.message : 'Connection test failed.')
      try {
        await refreshOrgAiData(orgId)
      } catch {
        /* ignore */
      }
    } finally {
      setTestingId(null)
    }
  }

  function openCredentialDialog(entry: AiProviderCatalogEntry) {
    setCredentialDialogEntry(entry)
    setCredentialValue('')
  }

  async function handleCredentialSave() {
    if (orgId == null || credentialDialogEntry == null) return
    const trimmed = credentialValue.trim()
    if (!trimmed) {
      showError(
        credentialDialogEntry && credentialIsEndpointUrl(credentialDialogEntry.provider)
          ? 'Paste your resource endpoint URL before saving.'
          : 'Paste your API key before saving.',
      )
      return
    }
    const label = providerDisplayName(credentialDialogEntry.provider)
    setCredentialSaving(true)
    try {
      await putOrganizationIntegrationSecret(orgId, credentialDialogEntry.integration_key, trimmed)
      await refreshOrgAiData(orgId)
      setCredentialDialogEntry(null)
      setCredentialValue('')
      showMessage(`Saved credentials for ${label}.`)
    } catch (e: unknown) {
      showError(e instanceof Error ? e.message : 'Could not save credentials.')
    } finally {
      setCredentialSaving(false)
    }
  }

  async function handleRemoveCredential(entry: AiProviderCatalogEntry) {
    if (orgId == null) return
    const label = providerDisplayName(entry.provider)
    const ok = await showConfirm(
      `Remove saved credentials for ${label}? Flows that need this provider will fail until you add a key again.`,
      {
        title: 'Remove credentials',
        confirmLabel: 'Remove',
        destructive: true,
      },
    )
    if (!ok) return
    try {
      await deleteOrganizationIntegrationSecret(orgId, entry.integration_key)
      await refreshOrgAiData(orgId)
      showMessage('Credentials removed.')
    } catch (e: unknown) {
      showError(e instanceof Error ? e.message : 'Could not remove credentials.')
    }
  }

  function toggleCap(setter: Dispatch<SetStateAction<Set<string>>>, key: string, on: boolean) {
    setter((prev) => {
      const next = new Set(prev)
      if (on) next.add(key)
      else next.delete(key)
      return next
    })
  }

  function capabilityCheckboxes(
    selected: Set<string>,
    setter: Dispatch<SetStateAction<Set<string>>>,
    disabled?: boolean,
  ) {
    return (
      <div className="flex flex-col gap-2">
        <Label className="text-xs">Capabilities</Label>
        <div className="flex flex-wrap gap-4">
          {CAP_KEYS.map((key) => (
            <label key={key} className="flex items-center gap-2 text-sm cursor-pointer">
              <Checkbox
                checked={selected.has(key)}
                disabled={disabled}
                onCheckedChange={(c) => toggleCap(setter, key, c === true)}
              />
              <span>{CAP_LABEL[key]}</span>
            </label>
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6 w-full max-w-none min-w-0">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">AI models</h1>
          <p className="text-muted-foreground mt-2">
            Add approved models for your organization, save provider keys once for the whole organization, and keep
            pricing and connection checks up to date. Flow steps only offer models that are enabled for each project.
          </p>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Provider credentials</CardTitle>
          <CardDescription>
            Keys are saved for your whole organization and never shown again after you save. Use Test connection on each
            model to confirm your setup.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex justify-end pb-4">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => {
                const preferred =
                  providerCatalog.find((p) => !p.configured) ?? providerCatalog[0] ?? null
                if (preferred) {
                  openCredentialDialog(preferred)
                }
              }}
              disabled={loading || providerCatalog.length === 0}
            >
              <Plus className="h-4 w-4 mr-2" />
              Add provider credential
            </Button>
          </div>
          {loading ? (
            <div className="flex items-center gap-2 text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading credentials…
            </div>
          ) : providersError ? (
            <p className="text-sm text-destructive">{providersError}</p>
          ) : providerCatalog.length === 0 ? (
            <p className="text-sm text-muted-foreground">No provider slots available.</p>
          ) : (
            <ul className="divide-y rounded-md border">
              {providerCatalog.map((entry) => (
                <li
                  key={entry.integration_key}
                  className="flex flex-col gap-2 px-3 py-3 sm:flex-row sm:items-center sm:justify-between"
                >
                  <div className="min-w-0 space-y-1">
                    <div className="font-medium">{providerDisplayName(entry.provider)}</div>
                    <div className="text-xs text-muted-foreground">
                      {entry.configured
                        ? `Saved${
                            entry.updated_at
                              ? ` · Updated ${new Date(entry.updated_at).toLocaleString()}`
                              : ''
                          }`
                        : 'No key saved yet'}
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2 shrink-0">
                    <Button type="button" variant="outline" size="sm" onClick={() => openCredentialDialog(entry)}>
                      {entry.configured ? 'Replace key' : 'Add key'}
                    </Button>
                    {entry.configured ? (
                      <Button
                        type="button"
                        variant="destructive"
                        size="sm"
                        onClick={() => void handleRemoveCredential(entry)}
                      >
                        Remove
                      </Button>
                    ) : null}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="space-y-1.5">
            <CardTitle>Organization catalog</CardTitle>
            <CardDescription>
              Active models can be turned on or off per project. Disabled models stay in the catalog but won&apos;t be
              offered on new runs when a project hides them.
            </CardDescription>
          </div>
          <Button
            type="button"
            onClick={() => {
              resetAddForm()
              setAddOpen(true)
            }}
            disabled={loading || orgId == null}
            className="sm:mt-1"
          >
            <Plus className="h-4 w-4 mr-2" />
            Add model
          </Button>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex items-center gap-2 text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading models…
            </div>
          ) : error ? (
            <p className="text-sm text-destructive">{error}</p>
          ) : models.length === 0 ? (
            <p className="text-sm text-muted-foreground">No models yet. Use Add model to create one.</p>
          ) : (
            <ul className="divide-y rounded-md border">
              {models.map((m) => (
                <li key={m.id} className="flex flex-col gap-2 px-3 py-3 sm:flex-row sm:items-center sm:justify-between">
                  <div className="min-w-0 space-y-1">
                    <div className="font-medium">{m.name}</div>
                    <div className="text-xs text-muted-foreground truncate">
                      {m.provider} · {m.provider_model_id}
                    </div>
                    <div className="flex flex-wrap gap-1 pt-1">
                      <Badge
                        variant="outline"
                        className={
                          m.status === "active"
                            ? "bg-green-100 text-green-800 border-green-200"
                            : "bg-muted text-muted-foreground border-border"
                        }
                      >
                        {m.status === "active" ? "Active" : m.status}
                      </Badge>
                      {m.capabilities.map((c) => (
                        <Badge key={c} variant="outline">
                          {CAP_LABEL[c as (typeof CAP_KEYS)[number]] ?? c}
                        </Badge>
                      ))}
                      {m.latest_test_status ? (
                        <Badge variant="outline">
                          {(() => {
                            const st = String(m.latest_test_status ?? "").toLowerCase()
                            const at = m.latest_tested_at ? new Date(m.latest_tested_at) : null
                            const stamp = at && !Number.isNaN(at.getTime()) ? at.toLocaleString() : null
                            if (st === "succeeded") {
                              return `Last check: 🟢 ${stamp ?? "Succeeded"}`
                            }
                            if (st === "failed") {
                              return `Last check: 🔴 ${stamp ?? "Failed"}`
                            }
                            return `Last check: ${stamp ?? m.latest_test_status}`
                          })()}
                        </Badge>
                      ) : null}
                    </div>
                    {m.latest_test_error ? (
                      <p className="text-xs text-destructive pt-1">{m.latest_test_error}</p>
                    ) : null}
                  </div>
                  <div className="flex flex-wrap gap-2 shrink-0">
                    <Button type="button" variant="outline" size="sm" onClick={() => openEdit(m)}>
                      Edit
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={testingId === m.id}
                      onClick={() => handleTestConnection(m)}
                    >
                      {testingId === m.id ? (
                        <>
                          <Loader2 className="h-3 w-3 mr-1 animate-spin inline" />
                          Testing…
                        </>
                      ) : (
                        'Test connection'
                      )}
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Dialog
        open={addOpen}
        onOpenChange={(o) => {
          setAddOpen(o)
          if (!o) resetAddForm()
        }}
      >
        <DialogContent className="sm:max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Add model</DialogTitle>
            <DialogDescription>
              Start from a common preset or add a custom model using your provider&apos;s routing name for that model.
            </DialogDescription>
          </DialogHeader>
          <Tabs value={addTab} onValueChange={(v) => setAddTab(v as 'preset' | 'custom')}>
            <TabsList className="grid w-full grid-cols-2">
              <TabsTrigger value="preset">Preset</TabsTrigger>
              <TabsTrigger value="custom">Custom</TabsTrigger>
            </TabsList>
            <TabsContent value="preset" className="space-y-4 pt-4">
              <div className="space-y-2">
                <Label className="text-xs">Preset</Label>
                <Select value={presetCuratedId} onValueChange={setPresetCuratedId}>
                  <SelectTrigger className="text-sm">
                    <SelectValue placeholder="Choose a model" />
                  </SelectTrigger>
                  <SelectContent>
                    {(() => {
                      const providerOrder = [
                        'openai',
                        'anthropic',
                        'gemini',
                        'openrouter',
                        'azure',
                      ] as const
                      const byProvider = new Map<string, CuratedAiModelOption[]>()
                      for (const opt of curatedOptions) {
                        const key = String(opt.provider || '').toLowerCase() || 'other'
                        const list = byProvider.get(key) ?? []
                        list.push(opt)
                        byProvider.set(key, list)
                      }
                      const keys = [
                        ...providerOrder.filter((p) => byProvider.has(p)),
                        ...Array.from(byProvider.keys()).filter(
                          (k) => !providerOrder.includes(k as any),
                        ),
                      ]
                      const labelFor = (p: string): string => {
                        if (p === 'openai') return 'OpenAI'
                        if (p === 'anthropic') return 'Anthropic'
                        if (p === 'gemini') return 'Gemini'
                        if (p === 'openrouter') return 'OpenRouter'
                        if (p === 'azure') return 'Azure OpenAI'
                        return p ? p[0].toUpperCase() + p.slice(1) : 'Other'
                      }
                      return keys.map((providerKey, idx) => {
                        const opts = byProvider.get(providerKey) ?? []
                        return (
                          <SelectGroup key={providerKey}>
                            {idx > 0 ? <SelectSeparator /> : null}
                            <SelectLabel className="pl-2 text-xs text-muted-foreground">
                              {labelFor(providerKey)}
                            </SelectLabel>
                            {opts.map((o) => (
                              <SelectItem key={o.curated_id} value={o.curated_id} className="pl-10">
                                {o.label}
                              </SelectItem>
                            ))}
                          </SelectGroup>
                        )
                      })
                    })()}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="preset-name" className="text-xs">
                  Display name (optional)
                </Label>
                <Input
                  id="preset-name"
                  value={presetName}
                  onChange={(e) => setPresetName(e.target.value)}
                  placeholder="Defaults to the preset label"
                />
              </div>
              {capabilityCheckboxes(presetCaps, setPresetCaps)}
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-2">
                  <Label htmlFor="preset-currency" className="text-xs">
                    Currency
                  </Label>
                  <Input
                    id="preset-currency"
                    value={presetCurrency}
                    onChange={(e) => setPresetCurrency(e.target.value)}
                    maxLength={3}
                  />
                </div>
              </div>
              <p className="text-xs text-muted-foreground">
                Optional usage prices are per token and feed run cost estimates.
              </p>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-2">
                  <Label htmlFor="preset-pin" className="text-xs">
                    Input usage price (optional)
                  </Label>
                  <Input
                    id="preset-pin"
                    value={presetPriceIn}
                    onChange={(e) => setPresetPriceIn(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="preset-pout" className="text-xs">
                    Output usage price (optional)
                  </Label>
                  <Input
                    id="preset-pout"
                    value={presetPriceOut}
                    onChange={(e) => setPresetPriceOut(e.target.value)}
                  />
                </div>
              </div>
            </TabsContent>
            <TabsContent value="custom" className="space-y-4 pt-4">
              <div className="space-y-2">
                <Label htmlFor="cust-name" className="text-xs">
                  Display name
                </Label>
                <Input id="cust-name" value={customName} onChange={(e) => setCustomName(e.target.value)} />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-2">
                  <Label htmlFor="cust-prov" className="text-xs">
                    Provider
                  </Label>
                  <Input
                    id="cust-prov"
                    value={customProvider}
                    onChange={(e) => setCustomProvider(e.target.value)}
                    placeholder="openai"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="cust-mid" className="text-xs">
                    Model id
                  </Label>
                  <Input
                    id="cust-mid"
                    value={customProviderModelId}
                    onChange={(e) => setCustomProviderModelId(e.target.value)}
                    placeholder="Provider model name"
                  />
                </div>
              </div>
              {capabilityCheckboxes(customCaps, setCustomCaps)}
              <div className="space-y-2">
                <Label htmlFor="cust-currency" className="text-xs">
                  Currency
                </Label>
                <Input
                  id="cust-currency"
                  value={customCurrency}
                  onChange={(e) => setCustomCurrency(e.target.value)}
                  maxLength={3}
                />
              </div>
              <p className="text-xs text-muted-foreground">
                Optional usage prices are per token and feed run cost estimates.
              </p>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-2">
                  <Label htmlFor="cust-pin" className="text-xs">
                    Input usage price (optional)
                  </Label>
                  <Input id="cust-pin" value={customPriceIn} onChange={(e) => setCustomPriceIn(e.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="cust-pout" className="text-xs">
                    Output usage price (optional)
                  </Label>
                  <Input id="cust-pout" value={customPriceOut} onChange={(e) => setCustomPriceOut(e.target.value)} />
                </div>
              </div>
            </TabsContent>
          </Tabs>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setAddOpen(false)}>
              Cancel
            </Button>
            <Button type="button" disabled={submitting} onClick={() => void handleAddSubmit()}>
              {submitting ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin inline" />
                  Saving…
                </>
              ) : (
                'Add'
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={editRow != null} onOpenChange={(o) => !o && setEditRow(null)}>
        <DialogContent className="sm:max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Edit model</DialogTitle>
            <DialogDescription>
              Update how this model appears, whether it is active, capabilities, and optional usage pricing for
              estimates.
            </DialogDescription>
          </DialogHeader>
          {editRow ? (
            <div className="space-y-4 py-2">
              <div className="text-xs text-muted-foreground">
                {editRow.provider} · {editRow.provider_model_id}
              </div>
              <div className="space-y-2">
                <Label htmlFor="edit-name" className="text-xs">
                  Display name
                </Label>
                <Input id="edit-name" value={editName} onChange={(e) => setEditName(e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label className="text-xs">Status</Label>
                <Select value={editStatus} onValueChange={(v) => setEditStatus(v as 'active' | 'disabled')}>
                  <SelectTrigger className="text-sm">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="active">Active</SelectItem>
                    <SelectItem value="disabled">Disabled</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              {capabilityCheckboxes(editCaps, setEditCaps)}
              <div className="space-y-2">
                <Label htmlFor="edit-currency" className="text-xs">
                  Currency
                </Label>
                <Input id="edit-currency" value={editCurrency} onChange={(e) => setEditCurrency(e.target.value)} maxLength={3} />
              </div>
              <p className="text-xs text-muted-foreground">Per token. Clear a field to remove pricing for estimates.</p>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-2">
                  <Label htmlFor="edit-pin" className="text-xs">
                    Input usage price
                  </Label>
                  <Input id="edit-pin" value={editPriceIn} onChange={(e) => setEditPriceIn(e.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="edit-pout" className="text-xs">
                    Output usage price
                  </Label>
                  <Input id="edit-pout" value={editPriceOut} onChange={(e) => setEditPriceOut(e.target.value)} />
                </div>
              </div>
            </div>
          ) : null}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setEditRow(null)}>
              Cancel
            </Button>
            <Button type="button" disabled={submitting || editRow == null} onClick={() => void handleEditSave()}>
              {submitting ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin inline" />
                  Saving…
                </>
              ) : (
                'Save'
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={credentialDialogEntry != null}
        onOpenChange={(open) => {
          if (!open) {
            setCredentialDialogEntry(null)
            setCredentialValue('')
          }
        }}
      >
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>
              {credentialDialogEntry
                ? `${providerDisplayName(credentialDialogEntry.provider)} credentials`
                : 'Credentials'}
            </DialogTitle>
            <DialogDescription>
              {credentialDialogEntry && credentialIsEndpointUrl(credentialDialogEntry.provider) ? (
                <>
                  Paste the resource endpoint URL from your Azure account (for example from the Azure portal). You
                  won&apos;t be able to view it here again—you can replace or remove it anytime.
                </>
              ) : (
                <>
                  Paste the API key from your provider account. You won&apos;t be able to view it here again—you can
                  replace or remove it anytime.
                </>
              )}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2 py-2">
            <Label htmlFor="credential-secret" className="text-xs">
              {credentialDialogEntry && credentialIsEndpointUrl(credentialDialogEntry.provider)
                ? 'Resource endpoint URL'
                : 'API key'}
            </Label>
            <Textarea
              id="credential-secret"
              value={credentialValue}
              onChange={(e) => setCredentialValue(e.target.value)}
              autoComplete="off"
              spellCheck={false}
              className="font-mono text-sm min-h-[88px]"
              placeholder={
                credentialDialogEntry && credentialIsEndpointUrl(credentialDialogEntry.provider)
                  ? 'https://your-resource.openai.azure.com/'
                  : 'Paste key…'
              }
            />
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                setCredentialDialogEntry(null)
                setCredentialValue('')
              }}
            >
              Cancel
            </Button>
            <Button type="button" disabled={credentialSaving} onClick={() => void handleCredentialSave()}>
              {credentialSaving ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin inline" />
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
