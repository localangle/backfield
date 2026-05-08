import { useCallback, useEffect, useMemo, useState } from 'react'
import { useAppMessage } from '@/components/AppMessageProvider'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
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
  createOrganizationAiCredential,
  createOrganizationAiModel,
  deleteOrganizationAiModel,
  deleteOrganizationIntegrationSecret,
  fetchMe,
  listAiCredentialsCatalog,
  listAiModelCuratedOptions,
  listOrganizationAiModels,
  patchOrganizationAiModel,
  patchOrganizationIntegrationSecret,
  testOrganizationAiModelConnection,
  type AiCredentialCatalogEntry,
  type AiModelConfigPatchInput,
  type AiModelConfigRow,
  type CuratedAiModelOption,
  type IntegrationSecretPatchInput,
} from '@/lib/core-api'
import { groupCuratedOptionsForPresetUi } from '@/lib/ai-curated-presets'
import { Loader2, Plus } from 'lucide-react'

const CAP_KEYS = ['text', 'json', 'vision'] as const

/** API + DB store usage prices per token; inputs show per 1M tokens for readability. */
const TOKENS_PER_MILLION = 1_000_000

function formatPriceNumberForInputField(n: number): string {
  if (!Number.isFinite(n)) return String(n)
  const fixed = n.toLocaleString(undefined, {
    useGrouping: false,
    maximumFractionDigits: 18,
  })
  return fixed.replace(/(\.\d*?[1-9])0+$/g, '$1').replace(/\.0+$/g, '').replace(/\.$/g, '')
}

/** Convert stored per-token price to a display string in “per 1M tokens” units. */
function perTokenToPerMillionDisplay(v: unknown): string {
  if (v == null || v === '') return ''
  const n = Number(v)
  if (!Number.isFinite(n)) return String(v)
  return formatPriceNumberForInputField(n * TOKENS_PER_MILLION)
}

function normalizeCapabilityList(selected: Set<string>): string[] {
  return CAP_KEYS.filter((k) => selected.has(k))
}

function catalogEntryPrimaryTitle(entry: AiCredentialCatalogEntry): string {
  const custom = entry.display_name?.trim()
  if (custom) return custom
  return 'Saved credential'
}

function customCredentialSelectLabel(c: AiCredentialCatalogEntry): string {
  const base = catalogEntryPrimaryTitle(c)
  if (c.has_api_base) return `${base} (endpoint URL set)`
  return base
}

function credentialLinkedModelsSummary(entry: AiCredentialCatalogEntry): string {
  const models = entry.linked_catalog_models ?? []
  if (models.length === 0) return 'Not linked to a model yet'
  if (models.length === 1) return `Linked to model: ${models[0].name}`
  const preview = models
    .slice(0, 3)
    .map((m) => m.name)
    .join(', ')
  const tail = models.length > 3 ? ` (+${models.length - 3} more)` : ''
  return `Linked to ${models.length} models: ${preview}${tail}`
}

export default function AiModelsSettingsPage() {
  const { showConfirm, showError } = useAppMessage()
  const [orgId, setOrgId] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [models, setModels] = useState<AiModelConfigRow[]>([])
  const [addOpen, setAddOpen] = useState(false)
  const [editRow, setEditRow] = useState<AiModelConfigRow | null>(null)
  const [testingId, setTestingId] = useState<string | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)
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
  const [presetIntegrationSecretId, setPresetIntegrationSecretId] = useState('')

  const [customName, setCustomName] = useState('')
  const [customLitellmModel, setCustomLitellmModel] = useState('')
  const [customIntegrationSecretId, setCustomIntegrationSecretId] = useState('')
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
  const [editLitellmModel, setEditLitellmModel] = useState('')
  const [editIntegrationSecretId, setEditIntegrationSecretId] = useState('')

  const [vendorCredModalOpen, setVendorCredModalOpen] = useState(false)
  const [vendorCredEditIntegrationKey, setVendorCredEditIntegrationKey] = useState<string | null>(null)
  const [vendorCredDisplayName, setVendorCredDisplayName] = useState('')
  const [vendorCredApiBase, setVendorCredApiBase] = useState('')
  const [vendorCredSecret, setVendorCredSecret] = useState('')
  const [vendorCredSaving, setVendorCredSaving] = useState(false)
  const [removingCredentialKey, setRemovingCredentialKey] = useState<string | null>(null)

  const [credentialCatalog, setCredentialCatalog] = useState<AiCredentialCatalogEntry[]>([])
  const [credentialsError, setCredentialsError] = useState<string | null>(null)

  const credentialsAvailableForNewModels = useMemo(
    () => credentialCatalog.filter((e) => e.integration_secret_id != null),
    [credentialCatalog],
  )

  const editCredentialChoices = useMemo(() => {
    if (!editRow) return []
    return credentialCatalog.filter((e) => e.integration_secret_id != null)
  }, [credentialCatalog, editRow])

  const curatedPresetSections = useMemo(
    () => groupCuratedOptionsForPresetUi(curatedOptions),
    [curatedOptions],
  )

  const refreshOrgAiData = useCallback(async (oid: number): Promise<AiModelConfigRow[]> => {
    const settled = await Promise.allSettled([listOrganizationAiModels(oid), listAiCredentialsCatalog(oid)])
    const modelsResult = settled[0]
    const credCatalogResult = settled[1]
    let nextModels: AiModelConfigRow[] = []
    if (modelsResult.status === 'fulfilled') {
      nextModels = modelsResult.value
      setModels(nextModels)
      setError(null)
    } else {
      setModels([])
      const r = modelsResult.reason
      setError(r instanceof Error ? r.message : 'Could not load catalog.')
    }
    if (credCatalogResult.status === 'fulfilled') {
      setCredentialCatalog(credCatalogResult.value)
      setCredentialsError(null)
    } else {
      setCredentialCatalog([])
      const r = credCatalogResult.reason
      setCredentialsError(r instanceof Error ? r.message : 'Could not load API credentials.')
    }
    return nextModels
  }, [])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      setError(null)
      setCredentialsError(null)
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
          setCredentialCatalog([])
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
      const nextIn = perTokenToPerMillionDisplay(opt.input_token_price)
      const nextOut = perTokenToPerMillionDisplay(opt.output_token_price)

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
    setPresetIntegrationSecretId('')
    setCustomName('')
    setCustomLitellmModel('')
    setCustomIntegrationSecretId('')
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
    setEditPriceIn(perTokenToPerMillionDisplay(row.input_token_price))
    setEditPriceOut(perTokenToPerMillionDisplay(row.output_token_price))
    setEditLitellmModel(row.litellm_model?.trim() ?? '')
    setEditIntegrationSecretId(
      row.integration_secret_id != null ? String(row.integration_secret_id) : '',
    )
  }

  function resetVendorCredModal() {
    setVendorCredModalOpen(false)
    setVendorCredEditIntegrationKey(null)
    setVendorCredDisplayName('')
    setVendorCredApiBase('')
    setVendorCredSecret('')
  }

  function openAddVendorCredentialModal() {
    setVendorCredEditIntegrationKey(null)
    setVendorCredDisplayName('')
    setVendorCredApiBase('')
    setVendorCredSecret('')
    setVendorCredModalOpen(true)
  }

  function openEditVendorCredentialModal(entry: AiCredentialCatalogEntry) {
    setVendorCredEditIntegrationKey(entry.integration_key)
    setVendorCredDisplayName(entry.display_name?.trim() ?? '')
    setVendorCredApiBase('')
    setVendorCredSecret('')
    setVendorCredModalOpen(true)
  }

  /** Parses “per 1M tokens” fields from the UI into per-token values for the API. */
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
      if (!Number.isFinite(n) || n < 0) {
        throw new Error('Input usage price must be a valid number (per 1 million tokens).')
      }
      out.input_token_price = n / TOKENS_PER_MILLION
    }
    if (to === '') out.output_token_price = null
    else {
      const n = Number(to)
      if (!Number.isFinite(n) || n < 0) {
        throw new Error('Output usage price must be a valid number (per 1 million tokens).')
      }
      out.output_token_price = n / TOKENS_PER_MILLION
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
        const sid = Number(presetIntegrationSecretId)
        if (!presetIntegrationSecretId.trim() || !Number.isFinite(sid)) {
          showError('Choose an API credential for this preset.')
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
          integration_secret_id: sid,
          ...prices,
        })
      } else {
        if (!customName.trim()) {
          showError('Display name is required.')
          return
        }
        const lm = customLitellmModel.trim()
        if (!lm) {
          showError('Enter the model routing string for this vendor (for example dashscope/qwen-turbo).')
          return
        }
        const sid = Number(customIntegrationSecretId)
        if (!customIntegrationSecretId.trim() || !Number.isFinite(sid)) {
          showError('Choose a saved API credential for this model.')
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
          litellm_model: lm,
          integration_secret_id: sid,
          capabilities: caps,
          currency: customCurrency.trim().toUpperCase() || 'USD',
          ...prices,
        })
      }
      await refreshOrgAiData(orgId)
      setAddOpen(false)
      resetAddForm()
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
      const patchBody: AiModelConfigPatchInput = {
        name: editName.trim(),
        status: editStatus,
        capabilities: caps,
        currency: editCurrency.trim().toUpperCase(),
        ...prices,
      }
      const usesLitellmRouting = Boolean(editRow.litellm_model?.trim())
      const sid = Number(editIntegrationSecretId)
      if (!editIntegrationSecretId.trim() || !Number.isFinite(sid)) {
        showError('Choose an API credential.')
        return
      }
      if (usesLitellmRouting) {
        const el = editLitellmModel.trim()
        if (!el) {
          showError('Model routing string is required for this model.')
          return
        }
        patchBody.litellm_model = el
        patchBody.integration_secret_id = sid
      } else if (editRow.integration_secret_id !== sid) {
        patchBody.integration_secret_id = sid
      }
      await patchOrganizationAiModel(orgId, editRow.id, patchBody)
      await refreshOrgAiData(orgId)
      setEditRow(null)
    } catch (e: unknown) {
      showError(e instanceof Error ? e.message : 'Could not update model.')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleDeleteCatalogModel(row: AiModelConfigRow) {
    if (orgId == null) return
    const confirmed = await showConfirm(
      `Remove "${row.name}" from your organization catalog? Project availability choices that pointed at this model are cleared. This cannot be undone.`,
      {
        destructive: true,
        confirmLabel: 'Remove',
        title: 'Remove model',
      },
    )
    if (!confirmed) return
    setDeletingId(row.id)
    try {
      await deleteOrganizationAiModel(orgId, row.id)
      await refreshOrgAiData(orgId)
      setEditRow((prev) => (prev?.id === row.id ? null : prev))
    } catch (e: unknown) {
      showError(e instanceof Error ? e.message : 'Could not remove model.')
    } finally {
      setDeletingId(null)
    }
  }

  async function handleTestConnection(row: AiModelConfigRow) {
    if (orgId == null) return
    setTestingId(row.id)
    try {
      await testOrganizationAiModelConnection(orgId, row.id)
      const after = await refreshOrgAiData(orgId)
      const updated = after.find((m) => m.id === row.id) ?? null
      const status = (updated?.latest_test_status || '').toLowerCase()
      if (status === 'failed') {
        showError('Connection test failed. Status updated for this model.')
      }
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

  async function handleVendorCredentialSave() {
    if (orgId == null || !vendorCredModalOpen) return
    const dnTrim = vendorCredDisplayName.trim()
    if (!dnTrim) {
      showError('Enter a display name for this credential.')
      return
    }
    const trimmedSecret = vendorCredSecret.trim()
    if (!vendorCredEditIntegrationKey && !trimmedSecret) {
      showError('Paste an API key before saving.')
      return
    }
    setVendorCredSaving(true)
    try {
      if (vendorCredEditIntegrationKey) {
        const body: IntegrationSecretPatchInput = {
          display_name: dnTrim,
        }
        if (trimmedSecret) body.value = trimmedSecret
        if (vendorCredApiBase.trim()) body.api_base = vendorCredApiBase.trim()
        await patchOrganizationIntegrationSecret(orgId, vendorCredEditIntegrationKey, body)
      } else {
        await createOrganizationAiCredential(orgId, {
          value: trimmedSecret,
          display_name: dnTrim,
          api_base: vendorCredApiBase.trim() ? vendorCredApiBase.trim() : null,
        })
      }
      await refreshOrgAiData(orgId)
      resetVendorCredModal()
    } catch (e: unknown) {
      showError(e instanceof Error ? e.message : 'Could not save credential.')
    } finally {
      setVendorCredSaving(false)
    }
  }

  async function handleRemoveCatalogCredential(entry: AiCredentialCatalogEntry) {
    if (orgId == null) return
    const label = catalogEntryPrimaryTitle(entry)
    const linked = entry.linked_catalog_models ?? []
    const description =
      linked.length === 0
        ? `Remove credential "${label}"? You can save a new key later if you need one again.`
        : linked.length === 1
          ? `Remove credential "${label}"? The model "${linked[0].name}" that uses it will be removed from your organization as well. This cannot be undone.`
          : `Remove credential "${label}"? All ${linked.length} catalog models that use it (${linked.map((m) => m.name).join(', ')}) will be removed. This cannot be undone.`
    const ok = await showConfirm(description, {
      title: 'Remove credential',
      confirmLabel: 'Remove',
      destructive: true,
    })
    if (!ok) return
    setRemovingCredentialKey(entry.integration_key)
    try {
      await deleteOrganizationIntegrationSecret(orgId, entry.integration_key)
      await refreshOrgAiData(orgId)
      setEditRow((prev) => {
        if (prev == null || entry.integration_secret_id == null) return prev
        return String(prev.integration_secret_id ?? '') === String(entry.integration_secret_id)
          ? null
          : prev
      })
    } catch (e: unknown) {
      showError(e instanceof Error ? e.message : 'Could not remove credential.')
    } finally {
      setRemovingCredentialKey(null)
    }
  }

  return (
    <div className="space-y-6 w-full max-w-none min-w-0">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">AI models</h1>
          <p className="text-muted-foreground mt-2">
            Manage organization-wide AI models and credentials.
          </p>
        </div>
      </div>

      <Card>
        <CardHeader className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="space-y-1.5">
            <CardTitle>Credentials</CardTitle>
            <CardDescription>
              Add API keys for your model providers here. Secrets are write-only. Paste a new key to replace one.
            </CardDescription>
          </div>
          <Button
            type="button"
            size="sm"
            className="bg-black text-white hover:bg-black/90 sm:mt-1"
            onClick={() => openAddVendorCredentialModal()}
            disabled={loading || orgId == null}
          >
            <Plus className="h-4 w-4 mr-2" />
            Add credential
          </Button>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex items-center gap-2 text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading credentials…
            </div>
          ) : credentialsError ? (
            <p className="text-sm text-destructive">{credentialsError}</p>
          ) : credentialCatalog.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No credentials yet. Use Add credential to store an API key, then link it when you add a model.
            </p>
          ) : (
            <ul className="divide-y rounded-md border">
              {credentialCatalog.map((entry) => (
                <li
                  key={entry.integration_key}
                  className="flex flex-col gap-2 px-3 py-3 sm:flex-row sm:items-center sm:justify-between"
                >
                  <div className="min-w-0 space-y-1">
                    <div className="font-medium">{catalogEntryPrimaryTitle(entry)}</div>
                    <div className="text-xs text-muted-foreground">
                      {credentialLinkedModelsSummary(entry)}
                      {entry.has_api_base ? ' · Endpoint URL saved' : ''}
                      {entry.updated_at ? ` · Updated ${new Date(entry.updated_at).toLocaleString()}` : ''}
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2 shrink-0">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={removingCredentialKey === entry.integration_key}
                      onClick={() => openEditVendorCredentialModal(entry)}
                    >
                      Update
                    </Button>
                    <Button
                      type="button"
                      variant="destructive"
                      size="sm"
                      className="font-normal"
                      disabled={removingCredentialKey === entry.integration_key}
                      onClick={() => void handleRemoveCatalogCredential(entry)}
                    >
                      {removingCredentialKey === entry.integration_key ? (
                        <>
                          <Loader2 className="h-3 w-3 mr-1 animate-spin inline" />
                          Removing…
                        </>
                      ) : (
                        'Remove'
                      )}
                    </Button>
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
            <CardTitle>Model catalog</CardTitle>
            <CardDescription>Add and enable AI models for your organization.</CardDescription>
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
                      {m.litellm_model?.trim()
                        ? m.litellm_model.trim()
                        : `${m.provider} · ${m.provider_model_id}`}
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
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={deletingId === m.id}
                      onClick={() => openEdit(m)}
                    >
                      Edit
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={testingId === m.id || deletingId === m.id}
                      onClick={() => void handleTestConnection(m)}
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
                    <Button
                      type="button"
                      variant="destructive"
                      size="sm"
                      className="font-normal"
                      disabled={
                        deletingId === m.id || testingId === m.id || (submitting && editRow?.id === m.id)
                      }
                      onClick={() => void handleDeleteCatalogModel(m)}
                    >
                      {deletingId === m.id ? (
                        <>
                          <Loader2 className="h-3 w-3 mr-1 animate-spin inline" />
                          Removing…
                        </>
                      ) : (
                        'Remove'
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
              Add a model to your organization and assign credentials.
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
                    {curatedPresetSections.map((section, sectionIdx) => (
                      <SelectGroup key={section.providerKey}>
                        {sectionIdx > 0 ? <SelectSeparator /> : null}
                        <SelectLabel className="pl-2 text-xs text-muted-foreground">
                          {section.providerLabel}
                        </SelectLabel>
                        {section.items.map((o) => (
                          <SelectItem key={o.curated_id} value={o.curated_id} className="pl-10">
                            {o.label}
                          </SelectItem>
                        ))}
                      </SelectGroup>
                    ))}
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
              <div className="space-y-2">
                <Label className="text-xs">API credential</Label>
                <Select
                  value={presetIntegrationSecretId || undefined}
                  onValueChange={(v) => setPresetIntegrationSecretId(v)}
                >
                  <SelectTrigger className="text-sm font-normal">
                    <SelectValue
                      placeholder={
                        credentialsAvailableForNewModels.length ? 'Choose credential' : 'Add a credential first'
                      }
                    />
                  </SelectTrigger>
                  <SelectContent>
                    {credentialsAvailableForNewModels.map((c) => (
                      <SelectItem key={c.integration_key} value={String(c.integration_secret_id ?? '')}>
                        {customCredentialSelectLabel(c)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <p className="text-xs text-muted-foreground">
                Optional. Price per 1 million tokens. Model costs are available on the{' '}
                <a
                  href="https://models.litellm.ai/"
                  className="underline underline-offset-2 hover:text-foreground"
                  target="_blank"
                  rel="noreferrer"
                >
                  LiteLLM models page
                </a>
                .
              </p>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-2">
                  <Label htmlFor="preset-pin" className="text-xs">
                    Input price per 1M tokens (optional)
                  </Label>
                  <div className="relative">
                    <span
                      className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
                      aria-hidden
                    >
                      $
                    </span>
                    <Input
                      id="preset-pin"
                      value={presetPriceIn}
                      onChange={(e) => setPresetPriceIn(e.target.value)}
                      className="pl-7"
                    />
                  </div>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="preset-pout" className="text-xs">
                    Output price per 1M tokens (optional)
                  </Label>
                  <div className="relative">
                    <span
                      className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
                      aria-hidden
                    >
                      $
                    </span>
                    <Input
                      id="preset-pout"
                      value={presetPriceOut}
                      onChange={(e) => setPresetPriceOut(e.target.value)}
                      className="pl-7"
                    />
                  </div>
                </div>
              </div>
            </TabsContent>
            <TabsContent value="custom" className="space-y-4 pt-4">
              <p className="text-xs text-muted-foreground">
                Choose any LiteLLM supported model from{' '}
                <a
                  href="https://models.litellm.ai/"
                  className="underline underline-offset-2 hover:text-foreground"
                  target="_blank"
                  rel="noreferrer"
                >
                  this list
                </a>
                .
              </p>
              <div className="space-y-2">
                <Label htmlFor="cust-name" className="text-xs">
                  Display name
                </Label>
                <Input
                  id="cust-name"
                  value={customName}
                  onChange={(e) => setCustomName(e.target.value)}
                  placeholder="ex. Claude Haiku 4.5 (Azure)"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="cust-litellm" className="text-xs">
                  Model routing string
                </Label>
                <Input
                  id="cust-litellm"
                  value={customLitellmModel}
                  onChange={(e) => setCustomLitellmModel(e.target.value)}
                  placeholder="ex. azure_ai/claude-haiku-4-5"
                  className="font-mono text-sm"
                />
                <p className="text-xs text-muted-foreground">Full model name string from LiteLLM</p>
              </div>
              <div className="space-y-2">
                <Label className="text-xs">API credential</Label>
                <Select
                  value={customIntegrationSecretId || undefined}
                  onValueChange={(v) => setCustomIntegrationSecretId(v)}
                >
                  <SelectTrigger className="text-sm font-normal">
                    <SelectValue
                      placeholder={
                        credentialsAvailableForNewModels.length ? 'Choose credential' : 'Add a credential first'
                      }
                    />
                  </SelectTrigger>
                  <SelectContent>
                    {credentialsAvailableForNewModels.map((c) => (
                      <SelectItem key={c.integration_key} value={String(c.integration_secret_id ?? '')}>
                        {customCredentialSelectLabel(c)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <p className="text-xs text-muted-foreground">
                Optional. Price per 1 million tokens. Model costs are available on the{' '}
                <a
                  href="https://models.litellm.ai/"
                  className="underline underline-offset-2 hover:text-foreground"
                  target="_blank"
                  rel="noreferrer"
                >
                  LiteLLM models page
                </a>
                .
              </p>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-2">
                  <Label htmlFor="cust-pin" className="text-xs">
                    Input price per 1M tokens (optional)
                  </Label>
                  <div className="relative">
                    <span
                      className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
                      aria-hidden
                    >
                      $
                    </span>
                    <Input
                      id="cust-pin"
                      value={customPriceIn}
                      onChange={(e) => setCustomPriceIn(e.target.value)}
                      className="pl-7"
                    />
                  </div>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="cust-pout" className="text-xs">
                    Output price per 1M tokens (optional)
                  </Label>
                  <div className="relative">
                    <span
                      className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
                      aria-hidden
                    >
                      $
                    </span>
                    <Input
                      id="cust-pout"
                      value={customPriceOut}
                      onChange={(e) => setCustomPriceOut(e.target.value)}
                      className="pl-7"
                    />
                  </div>
                </div>
              </div>
            </TabsContent>
          </Tabs>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setAddOpen(false)}>
              Cancel
            </Button>
            <Button
              type="button"
              className="bg-black text-white hover:bg-black/90"
              disabled={submitting}
              onClick={() => void handleAddSubmit()}
            >
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
              Update credential, display name, status, and optional usage pricing.
            </DialogDescription>
          </DialogHeader>
          {editRow ? (
            <Tabs
              key={editRow.id}
              value={editRow.litellm_model?.trim() ? 'custom' : 'preset'}
              className="w-full"
            >
              <TabsList className="grid w-full grid-cols-2">
                <TabsTrigger value="preset" disabled={Boolean(editRow.litellm_model?.trim())}>
                  Preset
                </TabsTrigger>
                <TabsTrigger value="custom" disabled={!editRow.litellm_model?.trim()}>
                  Custom
                </TabsTrigger>
              </TabsList>
              <TabsContent value="preset" className="space-y-4 pt-4">
                <div className="space-y-2">
                  <Label className="text-xs">Preset</Label>
                  <div className="rounded-md border border-input bg-muted/30 px-3 py-2 text-sm">
                    {editRow.provider} · {editRow.provider_model_id}
                  </div>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="edit-preset-name" className="text-xs">
                    Display name (optional)
                  </Label>
                  <Input
                    id="edit-preset-name"
                    value={editName}
                    onChange={(e) => setEditName(e.target.value)}
                    placeholder="Defaults to the catalog label"
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-xs">API credential</Label>
                  <Select value={editIntegrationSecretId} onValueChange={(v) => setEditIntegrationSecretId(v)}>
                    <SelectTrigger className="text-sm font-normal">
                      <SelectValue
                        placeholder={
                          editCredentialChoices.length ? 'Choose credential' : 'Add a credential first'
                        }
                      />
                    </SelectTrigger>
                    <SelectContent>
                      {editCredentialChoices.map((c) => (
                        <SelectItem key={c.integration_key} value={String(c.integration_secret_id ?? '')}>
                          {customCredentialSelectLabel(c)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
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
                <p className="text-xs text-muted-foreground">
                  Optional. Price per 1 million tokens. Model costs are available on the{' '}
                  <a
                    href="https://models.litellm.ai/"
                    className="underline underline-offset-2 hover:text-foreground"
                    target="_blank"
                    rel="noreferrer"
                  >
                    LiteLLM models page
                  </a>
                  .
                </p>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-2">
                    <Label htmlFor="edit-preset-pin" className="text-xs">
                      Input price per 1M tokens (optional)
                    </Label>
                    <div className="relative">
                      <span
                        className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
                        aria-hidden
                      >
                        $
                      </span>
                      <Input
                        id="edit-preset-pin"
                        value={editPriceIn}
                        onChange={(e) => setEditPriceIn(e.target.value)}
                        className="pl-7"
                      />
                    </div>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="edit-preset-pout" className="text-xs">
                      Output price per 1M tokens (optional)
                    </Label>
                    <div className="relative">
                      <span
                        className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
                        aria-hidden
                      >
                        $
                      </span>
                      <Input
                        id="edit-preset-pout"
                        value={editPriceOut}
                        onChange={(e) => setEditPriceOut(e.target.value)}
                        className="pl-7"
                      />
                    </div>
                  </div>
                </div>
              </TabsContent>
              <TabsContent value="custom" className="space-y-4 pt-4">
                <p className="text-xs text-muted-foreground">
                  Choose any LiteLLM supported model from{' '}
                  <a
                    href="https://models.litellm.ai/"
                    className="underline underline-offset-2 hover:text-foreground"
                    target="_blank"
                    rel="noreferrer"
                  >
                    this list
                  </a>
                  .
                </p>
                <div className="space-y-2">
                  <Label htmlFor="edit-cust-name" className="text-xs">
                    Display name
                  </Label>
                  <Input
                    id="edit-cust-name"
                    value={editName}
                    onChange={(e) => setEditName(e.target.value)}
                    placeholder="ex. Claude Haiku 4.5 (Azure)"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="edit-litellm" className="text-xs">
                    Model routing string
                  </Label>
                  <Input
                    id="edit-litellm"
                    value={editLitellmModel}
                    onChange={(e) => setEditLitellmModel(e.target.value)}
                    placeholder="ex. azure_ai/claude-haiku-4-5"
                    className="font-mono text-sm"
                  />
                  <p className="text-xs text-muted-foreground">Full model name string from LiteLLM</p>
                </div>
                <div className="space-y-2">
                  <Label className="text-xs">API credential</Label>
                  <Select value={editIntegrationSecretId} onValueChange={(v) => setEditIntegrationSecretId(v)}>
                    <SelectTrigger className="text-sm font-normal">
                      <SelectValue
                        placeholder={
                          editCredentialChoices.length ? 'Choose credential' : 'Add a credential first'
                        }
                      />
                    </SelectTrigger>
                    <SelectContent>
                      {editCredentialChoices.map((c) => (
                        <SelectItem key={c.integration_key} value={String(c.integration_secret_id ?? '')}>
                          {customCredentialSelectLabel(c)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
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
                <p className="text-xs text-muted-foreground">
                  Optional. Price per 1 million tokens. Model costs are available on the{' '}
                  <a
                    href="https://models.litellm.ai/"
                    className="underline underline-offset-2 hover:text-foreground"
                    target="_blank"
                    rel="noreferrer"
                  >
                    LiteLLM models page
                  </a>
                  .
                </p>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-2">
                    <Label htmlFor="edit-cust-pin" className="text-xs">
                      Input price per 1M tokens (optional)
                    </Label>
                    <div className="relative">
                      <span
                        className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
                        aria-hidden
                      >
                        $
                      </span>
                      <Input
                        id="edit-cust-pin"
                        value={editPriceIn}
                        onChange={(e) => setEditPriceIn(e.target.value)}
                        className="pl-7"
                      />
                    </div>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="edit-cust-pout" className="text-xs">
                      Output price per 1M tokens (optional)
                    </Label>
                    <div className="relative">
                      <span
                        className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
                        aria-hidden
                      >
                        $
                      </span>
                      <Input
                        id="edit-cust-pout"
                        value={editPriceOut}
                        onChange={(e) => setEditPriceOut(e.target.value)}
                        className="pl-7"
                      />
                    </div>
                  </div>
                </div>
              </TabsContent>
            </Tabs>
          ) : null}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setEditRow(null)}>
              Cancel
            </Button>
            <Button
              type="button"
              className="bg-black text-white hover:bg-black/90"
              disabled={submitting || editRow == null}
              onClick={() => void handleEditSave()}
            >
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
        open={vendorCredModalOpen}
        onOpenChange={(open) => {
          if (!open) resetVendorCredModal()
        }}
      >
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{vendorCredEditIntegrationKey ? 'Update credential' : 'Add credential'}</DialogTitle>
            <DialogDescription>
              {vendorCredEditIntegrationKey ? (
                <>
                  Paste a new key only if you want to replace the saved one. Leave the key blank to keep the current
                  secret; display name and endpoint URL updates apply right away.
                </>
              ) : (
                <>
                  Name this credential so your team can pick it when adding a model. Add an endpoint URL only if your
                  vendor needs one. Keys are encrypted and never shown again after saving.
                </>
              )}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-2">
              <Label htmlFor="vendor-cred-label" className="text-xs">
                Display name
              </Label>
              <Input
                id="vendor-cred-label"
                value={vendorCredDisplayName}
                onChange={(e) => setVendorCredDisplayName(e.target.value)}
                placeholder="e.g. OpenAI"
                maxLength={240}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="vendor-cred-base" className="text-xs">
                Endpoint URL (optional)
              </Label>
              <Input
                id="vendor-cred-base"
                value={vendorCredApiBase}
                onChange={(e) => setVendorCredApiBase(e.target.value)}
                placeholder="https://…"
                autoComplete="off"
              />
              <p className="text-xs text-muted-foreground">
                Only if your provider expects a base URL in addition to the key (for example, Azure OpenAI).
              </p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="vendor-cred-secret" className="text-xs">
                API key {vendorCredEditIntegrationKey ? '(optional — paste only to replace)' : ''}
              </Label>
              <Textarea
                id="vendor-cred-secret"
                value={vendorCredSecret}
                onChange={(e) => setVendorCredSecret(e.target.value)}
                autoComplete="off"
                spellCheck={false}
                className="font-mono text-sm min-h-[88px]"
                placeholder={vendorCredEditIntegrationKey ? 'Leave blank to keep current key' : 'Paste key…'}
              />
            </div>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => resetVendorCredModal()}>
              Cancel
            </Button>
            <Button
              type="button"
              className="bg-black text-white hover:bg-black/90"
              disabled={
                vendorCredSaving ||
                !vendorCredDisplayName.trim() ||
                (!vendorCredEditIntegrationKey && !vendorCredSecret.trim())
              }
              onClick={() => void handleVendorCredentialSave()}
            >
              {vendorCredSaving ? (
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
