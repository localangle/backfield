import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type Dispatch,
  type SetStateAction,
} from 'react'
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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  createOrganizationAiCredential,
  createOrganizationAiModel,
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

  const [credentialCatalog, setCredentialCatalog] = useState<AiCredentialCatalogEntry[]>([])
  const [credentialsError, setCredentialsError] = useState<string | null>(null)

  const credentialsAvailableForNewModels = useMemo(
    () => credentialCatalog.filter((e) => e.integration_secret_id != null && !e.assigned_model_config_id),
    [credentialCatalog],
  )

  const editCredentialChoices = useMemo(() => {
    if (!editRow) return []
    const sid = editRow.integration_secret_id
    return credentialCatalog.filter(
      (e) =>
        e.integration_secret_id != null &&
        (!e.assigned_model_config_id ||
          e.assigned_model_config_id === editRow.id ||
          (sid != null && String(e.integration_secret_id) === String(sid))),
    )
  }, [credentialCatalog, editRow])

  const refreshOrgAiData = useCallback(async (oid: number) => {
    const settled = await Promise.allSettled([listOrganizationAiModels(oid), listAiCredentialsCatalog(oid)])
    const modelsResult = settled[0]
    const credCatalogResult = settled[1]
    if (modelsResult.status === 'fulfilled') {
      setModels(modelsResult.value)
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
    setEditPriceIn(formatPriceField(row.input_token_price))
    setEditPriceOut(formatPriceField(row.output_token_price))
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

  async function handleVendorCredentialSave() {
    if (orgId == null || !vendorCredModalOpen) return
    const trimmedSecret = vendorCredSecret.trim()
    if (!vendorCredEditIntegrationKey && !trimmedSecret) {
      showError('Paste an API key before saving.')
      return
    }
    setVendorCredSaving(true)
    try {
      const dn = vendorCredDisplayName.trim() ? vendorCredDisplayName.trim() : null
      if (vendorCredEditIntegrationKey) {
        const body: IntegrationSecretPatchInput = {
          display_name: dn,
        }
        if (trimmedSecret) body.value = trimmedSecret
        if (vendorCredApiBase.trim()) body.api_base = vendorCredApiBase.trim()
        await patchOrganizationIntegrationSecret(orgId, vendorCredEditIntegrationKey, body)
      } else {
        await createOrganizationAiCredential(orgId, {
          value: trimmedSecret,
          display_name: dn,
          api_base: vendorCredApiBase.trim() ? vendorCredApiBase.trim() : null,
        })
      }
      await refreshOrgAiData(orgId)
      resetVendorCredModal()
      showMessage(vendorCredEditIntegrationKey ? 'Credential updated.' : 'Credential saved.')
    } catch (e: unknown) {
      showError(e instanceof Error ? e.message : 'Could not save credential.')
    } finally {
      setVendorCredSaving(false)
    }
  }

  async function handleRemoveCatalogCredential(entry: AiCredentialCatalogEntry) {
    if (orgId == null) return
    const label = catalogEntryPrimaryTitle(entry)
    const ok = await showConfirm(`Remove ${label}? Models that use this credential will fail until you link another key.`, {
      title: 'Remove credential',
      confirmLabel: 'Remove',
      destructive: true,
    })
    if (!ok) return
    try {
      await deleteOrganizationIntegrationSecret(orgId, entry.integration_key)
      await refreshOrgAiData(orgId)
      showMessage('Credential removed.')
    } catch (e: unknown) {
      showError(e instanceof Error ? e.message : 'Could not remove credential.')
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
            Add API credentials, then link each catalog model to one credential. Flow steps only offer models that are
            enabled for each project.
          </p>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>API credentials</CardTitle>
          <CardDescription>
            Each credential stores one vendor API key (and optional endpoint URL). Every catalog model must use exactly
            one credential for runs that resolve keys from the catalog. Secrets are write-only here—paste a new key to
            replace one.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap justify-end gap-2 pb-4">
            <Button
              type="button"
              size="sm"
              className="bg-black text-white hover:bg-black/90"
              onClick={() => openAddVendorCredentialModal()}
              disabled={loading || orgId == null}
            >
              <Plus className="h-4 w-4 mr-2" />
              Add credential
            </Button>
          </div>
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
                      {entry.assigned_model_name
                        ? `Linked to model: ${entry.assigned_model_name}`
                        : 'Not linked to a model yet'}
                      {entry.has_api_base ? ' · Endpoint URL saved' : ''}
                      {entry.updated_at ? ` · Updated ${new Date(entry.updated_at).toLocaleString()}` : ''}
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2 shrink-0">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => openEditVendorCredentialModal(entry)}
                    >
                      Update
                    </Button>
                    {!entry.assigned_model_config_id ? (
                      <Button
                        type="button"
                        variant="destructive"
                        size="sm"
                        onClick={() => void handleRemoveCatalogCredential(entry)}
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
              Link each model to one saved credential. Presets use templates from the product; custom entries use your own
              routing string from the vendor&apos;s docs.
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
                    {[...curatedOptions]
                      .sort((a, b) => a.label.localeCompare(b.label))
                      .map((o) => (
                        <SelectItem key={o.curated_id} value={o.curated_id}>
                          {o.label}
                        </SelectItem>
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
              <p className="text-xs text-muted-foreground">
                Use the exact routing string from your vendor&apos;s docs (for example{' '}
                <span className="font-mono">dashscope/qwen-turbo</span>). Add a credential above first, then pick it
                here.
              </p>
              <div className="space-y-2">
                <Label htmlFor="cust-name" className="text-xs">
                  Display name
                </Label>
                <Input id="cust-name" value={customName} onChange={(e) => setCustomName(e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="cust-litellm" className="text-xs">
                  Model routing string
                </Label>
                <Input
                  id="cust-litellm"
                  value={customLitellmModel}
                  onChange={(e) => setCustomLitellmModel(e.target.value)}
                  placeholder="provider/model-id"
                  className="font-mono text-sm"
                />
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
              Update how this model appears, whether it is active, capabilities, and optional usage pricing for
              estimates.
            </DialogDescription>
          </DialogHeader>
          {editRow ? (
            <div className="space-y-4 py-2">
              <div className="text-xs text-muted-foreground">
                {editRow.litellm_model?.trim()
                  ? editRow.litellm_model.trim()
                  : `${editRow.provider} · ${editRow.provider_model_id}`}
              </div>
              {editRow.litellm_model?.trim() ? (
                <div className="space-y-2">
                  <Label htmlFor="edit-litellm" className="text-xs">
                    Model routing string
                  </Label>
                  <Input
                    id="edit-litellm"
                    value={editLitellmModel}
                    onChange={(e) => setEditLitellmModel(e.target.value)}
                    className="font-mono text-sm"
                  />
                </div>
              ) : null}
              <div className="space-y-2">
                <Label className="text-xs">API credential</Label>
                <Select value={editIntegrationSecretId} onValueChange={(v) => setEditIntegrationSecretId(v)}>
                  <SelectTrigger className="text-sm font-normal">
                    <SelectValue placeholder="Choose credential" />
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
                  vendor needs one. Keys are never shown again after saving.
                </>
              )}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-2">
              <Label htmlFor="vendor-cred-label" className="text-xs">
                Display name (optional)
              </Label>
              <Input
                id="vendor-cred-label"
                value={vendorCredDisplayName}
                onChange={(e) => setVendorCredDisplayName(e.target.value)}
                placeholder="e.g. Qwen production"
                maxLength={240}
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
                Only if your provider expects a base URL in addition to the key (for example some OpenAI-compatible
                hosts).
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
              disabled={vendorCredSaving}
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
