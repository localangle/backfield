import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { AlertCircle, Plus } from 'lucide-react'

import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
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
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useAppMessage } from '@/components/AppMessageProvider'
import { SettingsScreenHeader } from '@/components/SettingsScreenHeader'
import { listGraphSummaries, type GraphSummary } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import {
  activateOrganizationWebhookEndpoint,
  createOrganizationWebhookEndpoint,
  deleteOrganizationWebhookEndpoint,
  disableOrganizationWebhookEndpoint,
  listOrganizationWebhookDeliveries,
  listOrganizationWebhookEndpoints,
  listOrganizationWebhookEventTypes,
  listOrgProjects,
  patchOrganizationWebhookEndpoint,
  replayOrganizationWebhookDelivery,
  rotateOrganizationWebhookSecret,
  testOrganizationWebhookEndpoint,
  type ProjectSummary,
  type WebhookDelivery,
  type WebhookEndpoint,
  type WebhookEventType,
  type WebhookOutcome,
} from '@/lib/core-api'

const OUTCOME_OPTIONS: { value: WebhookOutcome; label: string }[] = [
  { value: 'succeeded', label: 'Finished successfully' },
  { value: 'failed', label: 'Failed (including cancelled)' },
]

const RUN_COMPLETED_TYPE = 'agate.run.completed'

/** Product-language copy for each event type; unknown types fall back to the raw name. */
const EVENT_TYPE_COPY: Record<string, { label: string; group: string }> = {
  'agate.run.completed': { label: 'A run finishes', group: 'Runs and articles' },
  'agate.article.created': { label: 'A new article is saved', group: 'Runs and articles' },
  'agate.article.updated': { label: 'An article is updated', group: 'Runs and articles' },
  'stylebook.canonical.created': {
    label: 'A Stylebook entry is created',
    group: 'Stylebook entries',
  },
  'stylebook.canonical.updated': {
    label: 'A Stylebook entry is edited',
    group: 'Stylebook entries',
  },
  'stylebook.canonical.deleted': {
    label: 'A Stylebook entry is deleted',
    group: 'Stylebook entries',
  },
  'stylebook.canonical.merged': {
    label: 'Stylebook entries are combined',
    group: 'Stylebook entries',
  },
  'stylebook.canonical.evidence.changed': {
    label: "A Stylebook entry's supporting mentions change",
    group: 'Stylebook entries',
  },
}

function eventTypeLabel(eventType: string): string {
  return EVENT_TYPE_COPY[eventType]?.label ?? eventType
}

const STATUS_LABEL: Record<string, string> = {
  pending: 'Waiting for test',
  active: 'Active',
  paused: 'Paused',
  disabled: 'Turned off',
}

function statusBadgeVariant(status: string): 'success' | 'secondary' | 'destructive' | 'outline' {
  if (status === 'active') return 'success'
  if (status === 'paused') return 'destructive'
  if (status === 'pending') return 'secondary'
  return 'outline'
}

function formatWhen(value: string | null): string {
  if (!value) return '—'
  return new Date(value).toLocaleString()
}

function deliveryStateLabel(delivery: WebhookDelivery): string {
  if (delivery.state === 'delivered') return 'Delivered'
  if (delivery.state === 'failed') return 'Could not deliver'
  if (delivery.state === 'delivering') return 'Sending'
  return 'Waiting to send'
}

interface EndpointFormState {
  projectId: number | null
  name: string
  url: string
  /** One update type per webhook endpoint. */
  eventType: string
  allFlows: boolean
  flowIds: string[]
  outcomes: WebhookOutcome[]
}

function emptyForm(): EndpointFormState {
  return {
    projectId: null,
    name: '',
    url: '',
    eventType: RUN_COMPLETED_TYPE,
    allFlows: true,
    flowIds: [],
    outcomes: [],
  }
}

function formNeedsFlowChoice(
  form: EndpointFormState,
  available: WebhookEventType[],
): boolean {
  const selected = available.find((t) => t.event_type === form.eventType)
  return Boolean(selected?.flow_scoped)
}

function groupedEventTypes(
  available: WebhookEventType[],
): [string, WebhookEventType[]][] {
  const groups = new Map<string, WebhookEventType[]>()
  for (const eventType of available) {
    const group = EVENT_TYPE_COPY[eventType.event_type]?.group ?? 'Other'
    const rows = groups.get(group) ?? []
    rows.push(eventType)
    groups.set(group, rows)
  }
  return [...groups.entries()]
}

/** Flow checklist bound to the selected project; loads flows on project change. */
function FlowPicker({
  projectId,
  selected,
  onChange,
}: {
  projectId: number | null
  selected: string[]
  onChange: (flowIds: string[]) => void
}) {
  const [flows, setFlows] = useState<GraphSummary[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    let cancelled = false
    if (projectId == null) {
      setFlows([])
      return
    }
    setLoading(true)
    listGraphSummaries(projectId)
      .then((rows) => {
        if (!cancelled) setFlows(rows)
      })
      .catch(() => {
        if (!cancelled) setFlows([])
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [projectId])

  if (projectId == null) {
    return <p className="text-sm text-muted-foreground">Choose a project first.</p>
  }
  if (loading) {
    return <p className="text-sm text-muted-foreground">Loading flows…</p>
  }
  if (flows.length === 0) {
    return <p className="text-sm text-muted-foreground">This project has no flows yet.</p>
  }
  return (
    <div className="max-h-36 space-y-2 overflow-y-auto rounded-md border border-border p-3">
      {flows.map((flow) => {
        const id = String(flow.id)
        const checked = selected.includes(id)
        return (
          <label key={id} className="flex items-center gap-2 text-sm">
            <Checkbox
              checked={checked}
              onCheckedChange={(next) =>
                onChange(next ? [...selected, id] : selected.filter((f) => f !== id))
              }
            />
            <span className="truncate">{flow.name}</span>
          </label>
        )
      })}
    </div>
  )
}

/** Create/edit form shared by the New webhook dialog and endpoint editing. */
function EndpointFormFields({
  form,
  setForm,
  projects,
  projectLocked,
  eventTypes,
}: {
  form: EndpointFormState
  setForm: (next: EndpointFormState) => void
  projects: ProjectSummary[]
  projectLocked: boolean
  eventTypes: WebhookEventType[]
}) {
  const needsFlowChoice = formNeedsFlowChoice(form, eventTypes)
  const runCompletedSelected = form.eventType === RUN_COMPLETED_TYPE
  const outcomeValue =
    form.outcomes.length === 1 ? form.outcomes[0] : 'any'

  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label>Project</Label>
          <Select
            value={form.projectId != null ? String(form.projectId) : undefined}
            onValueChange={(value) =>
              setForm({ ...form, projectId: Number(value), flowIds: [] })
            }
            disabled={projectLocked}
          >
            <SelectTrigger>
              <SelectValue placeholder="Choose a project" />
            </SelectTrigger>
            <SelectContent>
              {projects.map((project) => (
                <SelectItem key={project.id} value={String(project.id)}>
                  {project.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="webhook-name">Name</Label>
          <Input
            id="webhook-name"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            placeholder="e.g. Newsroom CMS"
          />
        </div>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="webhook-url">Destination URL</Label>
        <Input
          id="webhook-url"
          value={form.url}
          onChange={(e) => setForm({ ...form, url: e.target.value })}
          placeholder="https://example.com/backfield-updates"
        />
        <p className="text-xs text-muted-foreground">
          Must be a secure (https) address your application can receive.
        </p>
      </div>

      <div className="space-y-1.5">
        <Label>Send an update when</Label>
        <Select
          value={form.eventType}
          onValueChange={(value) =>
            setForm({
              ...form,
              eventType: value,
              // Outcome filter only applies to run completions.
              outcomes: value === RUN_COMPLETED_TYPE ? form.outcomes : [],
            })
          }
        >
          <SelectTrigger>
            <SelectValue placeholder="Choose an update type" />
          </SelectTrigger>
          <SelectContent>
            {groupedEventTypes(eventTypes).map(([group, rows]) => (
              <SelectGroup key={group}>
                <SelectLabel>{group}</SelectLabel>
                {rows.map((row) => (
                  <SelectItem key={row.event_type} value={row.event_type}>
                    {eventTypeLabel(row.event_type)}
                  </SelectItem>
                ))}
              </SelectGroup>
            ))}
          </SelectContent>
        </Select>
        {form.eventType.startsWith('stylebook.') && (
          <p className="text-xs text-muted-foreground">
            Stylebook updates cover the whole project, regardless of flow.
          </p>
        )}
      </div>

      {needsFlowChoice && (
        <div className="space-y-1.5">
          <Label>Flows to watch</Label>
          <Select
            value={form.allFlows ? 'all' : 'specific'}
            onValueChange={(value) =>
              setForm({
                ...form,
                allFlows: value === 'all',
                flowIds: value === 'all' ? [] : form.flowIds,
              })
            }
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All flows in this project</SelectItem>
              <SelectItem value="specific">Specific flows</SelectItem>
            </SelectContent>
          </Select>
          {!form.allFlows && (
            <FlowPicker
              projectId={form.projectId}
              selected={form.flowIds}
              onChange={(flowIds) => setForm({ ...form, flowIds })}
            />
          )}
        </div>
      )}

      {runCompletedSelected && (
        <div className="space-y-1.5">
          <Label>Run results to include</Label>
          <Select
            value={outcomeValue}
            onValueChange={(value) =>
              setForm({
                ...form,
                outcomes:
                  value === 'succeeded' || value === 'failed' ? [value] : [],
              })
            }
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="any">Every result</SelectItem>
              {OUTCOME_OPTIONS.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}
    </div>
  )
}

/** One-time signing secret reveal plus the required first test delivery. */
function SecretRevealDialog({
  orgId,
  endpoint,
  secret,
  onClose,
  onEndpointUpdated,
}: {
  orgId: number
  endpoint: WebhookEndpoint
  secret: string
  onClose: () => void
  onEndpointUpdated: (endpoint: WebhookEndpoint) => void
}) {
  const [copied, setCopied] = useState(false)
  const [testing, setTesting] = useState(false)
  const [testMessage, setTestMessage] = useState<string | null>(null)
  const [testOk, setTestOk] = useState<boolean | null>(null)

  const runTest = async () => {
    setTesting(true)
    setTestMessage(null)
    try {
      const response = await testOrganizationWebhookEndpoint(orgId, endpoint.id)
      onEndpointUpdated(response.endpoint)
      setTestOk(response.result.ok)
      setTestMessage(
        response.result.ok
          ? 'Test delivery received. This webhook is now active.'
          : response.result.failure_summary ??
              'The destination did not accept the test delivery.',
      )
    } catch (e) {
      setTestOk(false)
      setTestMessage(e instanceof Error ? e.message : 'The test could not be sent.')
    } finally {
      setTesting(false)
    }
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Save your signing secret</DialogTitle>
          <DialogDescription>
            Use this secret in the receiving application to confirm updates really came
            from Backfield. It is shown only once.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <Input readOnly value={secret} className="font-mono text-xs" />
            <Button
              variant="outline"
              onClick={() => {
                void navigator.clipboard.writeText(secret)
                setCopied(true)
              }}
            >
              {copied ? 'Copied' : 'Copy'}
            </Button>
          </div>
          <Alert>
            <AlertCircle className="h-4 w-4" aria-hidden />
            <AlertDescription>
              Send a test delivery to turn this webhook on. Updates start flowing only
              after the destination accepts a test.
            </AlertDescription>
          </Alert>
          {testMessage != null && (
            <p className={testOk ? 'text-sm text-green-700' : 'text-sm text-destructive'}>
              {testMessage}
            </p>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Close
          </Button>
          <Button onClick={() => void runTest()} disabled={testing}>
            {testing ? 'Sending test…' : 'Send test delivery'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** Delivery history plus per-delivery replay for one endpoint. */
function DeliveryHistory({
  orgId,
  endpoint,
}: {
  orgId: number
  endpoint: WebhookEndpoint
}) {
  const { showError, showMessage } = useAppMessage()
  const [deliveries, setDeliveries] = useState<WebhookDelivery[] | null>(null)
  const [replaying, setReplaying] = useState<string | null>(null)

  const reload = useCallback(async () => {
    try {
      setDeliveries(await listOrganizationWebhookDeliveries(orgId, endpoint.id))
    } catch (e) {
      showError(e instanceof Error ? e.message : 'Could not load delivery history.')
    }
  }, [orgId, endpoint.id, showError])

  useEffect(() => {
    void reload()
  }, [reload])

  const replay = async (deliveryId: string) => {
    setReplaying(deliveryId)
    try {
      await replayOrganizationWebhookDelivery(orgId, endpoint.id, deliveryId)
      showMessage('The update will be sent again shortly.', { title: 'Resend queued' })
      await reload()
    } catch (e) {
      showError(e instanceof Error ? e.message : 'Could not resend this update.')
    } finally {
      setReplaying(null)
    }
  }

  if (deliveries == null) {
    return <p className="text-sm text-muted-foreground">Loading recent deliveries…</p>
  }
  if (deliveries.length === 0) {
    return <p className="text-sm text-muted-foreground">No deliveries yet.</p>
  }
  return (
    <div className="max-h-80 space-y-2 overflow-y-auto">
      {deliveries.map((delivery) => (
        <div
          key={delivery.id}
          className="flex items-start justify-between gap-3 rounded-md border border-border p-3"
        >
          <div className="min-w-0 space-y-1">
            <div className="flex flex-wrap items-center gap-2">
              <Badge
                variant={
                  delivery.state === 'delivered'
                    ? 'success'
                    : delivery.state === 'failed'
                      ? 'destructive'
                      : 'secondary'
                }
              >
                {deliveryStateLabel(delivery)}
              </Badge>
              {delivery.is_test && <Badge variant="outline">Test</Badge>}
              {delivery.is_replay && <Badge variant="outline">Resend</Badge>}
              <span className="text-xs text-muted-foreground">
                {formatWhen(delivery.created_at)}
              </span>
            </div>
            <div className="truncate text-sm">
              {delivery.is_test
                ? 'Test delivery'
                : eventTypeLabel(delivery.event_type)}
              {delivery.flow_name != null && (
                <span className="text-muted-foreground"> · {delivery.flow_name}</span>
              )}
              {delivery.run_id != null && (
                <span className="text-muted-foreground"> · run {delivery.run_id.slice(0, 8)}</span>
              )}
            </div>
            {delivery.failure_summary != null && delivery.state !== 'delivered' && (
              <p className="text-xs text-destructive">{delivery.failure_summary}</p>
            )}
            <p className="text-xs text-muted-foreground">
              {delivery.attempt_count} attempt{delivery.attempt_count === 1 ? '' : 's'}
              {delivery.last_status_code != null &&
                ` · last response ${delivery.last_status_code}`}
            </p>
          </div>
          {!delivery.is_test && (
            <Button
              size="sm"
              variant="outline"
              disabled={replaying === delivery.id}
              onClick={() => void replay(delivery.id)}
            >
              {replaying === delivery.id ? 'Resending…' : 'Resend'}
            </Button>
          )}
        </div>
      ))}
    </div>
  )
}

export default function WebhooksSettings() {
  const { organizationId } = useAuth()
  const { showConfirm, showError, showMessage } = useAppMessage()
  const [searchParams, setSearchParams] = useSearchParams()

  const [endpoints, setEndpoints] = useState<WebhookEndpoint[]>([])
  const [projects, setProjects] = useState<ProjectSummary[]>([])
  const [eventTypes, setEventTypes] = useState<WebhookEventType[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [createOpen, setCreateOpen] = useState(false)
  const [createForm, setCreateForm] = useState<EndpointFormState>(emptyForm())
  const [saving, setSaving] = useState(false)

  const [reveal, setReveal] = useState<{ endpoint: WebhookEndpoint; secret: string } | null>(null)
  const [detail, setDetail] = useState<WebhookEndpoint | null>(null)
  const [editOpen, setEditOpen] = useState(false)
  const [editForm, setEditForm] = useState<EndpointFormState>(emptyForm())
  const [busyAction, setBusyAction] = useState<string | null>(null)

  const reload = useCallback(async () => {
    if (organizationId == null) return
    try {
      const [rows, projectRows, eventTypeRows] = await Promise.all([
        listOrganizationWebhookEndpoints(organizationId),
        listOrgProjects(organizationId),
        listOrganizationWebhookEventTypes(organizationId),
      ])
      setEndpoints(rows)
      setProjects(projectRows)
      setEventTypes(eventTypeRows)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load webhooks.')
    } finally {
      setLoading(false)
    }
  }, [organizationId])

  useEffect(() => {
    void reload()
  }, [reload])

  // Flow-context shortcut: /settings/webhooks?create=1&project=<id>&flow=<flowId>
  useEffect(() => {
    if (searchParams.get('create') !== '1') return
    const projectParam = searchParams.get('project')
    const flowParam = searchParams.get('flow')
    setCreateForm({
      ...emptyForm(),
      projectId: projectParam != null ? Number(projectParam) : null,
      flowIds: flowParam != null ? [flowParam] : [],
      allFlows: flowParam == null,
    })
    setCreateOpen(true)
    setSearchParams({}, { replace: true })
  }, [searchParams, setSearchParams])

  const pausedEndpoints = useMemo(
    () => endpoints.filter((endpoint) => endpoint.status === 'paused'),
    [endpoints],
  )

  const updateEndpointInList = useCallback((updated: WebhookEndpoint) => {
    setEndpoints((prev) => prev.map((row) => (row.id === updated.id ? updated : row)))
    setDetail((prev) => (prev != null && prev.id === updated.id ? updated : prev))
  }, [])

  const submitCreate = async () => {
    if (organizationId == null || createForm.projectId == null) return
    setSaving(true)
    try {
      const created = await createOrganizationWebhookEndpoint(organizationId, {
        project_id: createForm.projectId,
        name: createForm.name.trim(),
        url: createForm.url.trim(),
        event_types: [createForm.eventType],
        all_flows: createForm.allFlows,
        ...(createForm.allFlows ? {} : { flow_ids: createForm.flowIds }),
        outcomes: createForm.outcomes.length > 0 ? createForm.outcomes : null,
      })
      setCreateOpen(false)
      setCreateForm(emptyForm())
      setEndpoints((prev) => [created.endpoint, ...prev])
      setReveal({ endpoint: created.endpoint, secret: created.signing_secret })
    } catch (e) {
      showError(e instanceof Error ? e.message : 'Could not create the webhook.')
    } finally {
      setSaving(false)
    }
  }

  const submitEdit = async () => {
    if (organizationId == null || detail == null) return
    setSaving(true)
    try {
      const updated = await patchOrganizationWebhookEndpoint(organizationId, detail.id, {
        name: editForm.name.trim(),
        ...(editForm.url.trim() !== '' ? { url: editForm.url.trim() } : {}),
        event_types: [editForm.eventType],
        all_flows: editForm.allFlows,
        ...(editForm.allFlows || editForm.flowIds.length === 0
          ? {}
          : { flow_ids: editForm.flowIds }),
        ...(editForm.outcomes.length > 0
          ? { outcomes: editForm.outcomes }
          : { clear_outcomes: true }),
      })
      updateEndpointInList(updated)
      setEditOpen(false)
      if (updated.status === 'pending') {
        showMessage(
          'Because the destination changed, send a new test delivery to turn this webhook back on.',
          { title: 'Test required' },
        )
      }
    } catch (e) {
      showError(e instanceof Error ? e.message : 'Could not save changes.')
    } finally {
      setSaving(false)
    }
  }

  const runAction = async (name: string, action: () => Promise<void>) => {
    setBusyAction(name)
    try {
      await action()
    } catch (e) {
      showError(e instanceof Error ? e.message : 'That action did not work.')
    } finally {
      setBusyAction(null)
    }
  }

  if (organizationId == null) return null

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <SettingsScreenHeader title="Webhooks">
          Send updates to another application when runs finish, articles are saved, or
          Stylebook entries change.
        </SettingsScreenHeader>
        <Button
          type="button"
          className="shrink-0"
          onClick={() => {
            setCreateForm(emptyForm())
            setCreateOpen(true)
          }}
        >
          <Plus className="mr-1 h-4 w-4" aria-hidden />
          New webhook
        </Button>
      </div>

      {pausedEndpoints.length > 0 && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" aria-hidden />
          <AlertDescription>
            {pausedEndpoints.length === 1
              ? `“${pausedEndpoints[0].name}” is paused because updates could not be delivered. Fix the destination, then resume it.`
              : `${pausedEndpoints.length} webhooks are paused because updates could not be delivered.`}
          </AlertDescription>
        </Alert>
      )}
      {error != null && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" aria-hidden />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      {loading ? (
        <p className="text-sm text-muted-foreground">Loading webhooks…</p>
      ) : endpoints.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No webhooks yet. Create one to notify another application when things happen in a
          project.
        </p>
      ) : (
        <div className="space-y-2">
          {endpoints.map((endpoint) => (
            <button
              key={endpoint.id}
              type="button"
              className="w-full rounded-lg border border-border bg-background p-4 text-left transition-colors hover:bg-muted/40"
              onClick={() => setDetail(endpoint)}
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium">{endpoint.name}</span>
                <Badge variant={statusBadgeVariant(endpoint.status)}>
                  {STATUS_LABEL[endpoint.status] ?? endpoint.status}
                </Badge>
                {endpoint.pending_deliveries > 0 && (
                  <Badge variant="secondary">{endpoint.pending_deliveries} waiting</Badge>
                )}
                {endpoint.failed_deliveries > 0 && (
                  <Badge variant="destructive">
                    {endpoint.failed_deliveries} not delivered
                  </Badge>
                )}
              </div>
              <div className="mt-1 text-sm text-muted-foreground">
                {endpoint.project_name ?? 'Project'} · {endpoint.destination_host} ·{' '}
                {eventTypeLabel(endpoint.event_types[0] ?? '')} ·{' '}
                {endpoint.all_flows
                  ? 'all flows'
                  : endpoint.flows.length > 0
                    ? `${endpoint.flows.length} flow${endpoint.flows.length === 1 ? '' : 's'}`
                    : 'project-wide'}
              </div>
              <div className="mt-1 text-xs text-muted-foreground">
                Last success {formatWhen(endpoint.last_success_at)} · Last failure{' '}
                {formatWhen(endpoint.last_failure_at)}
              </div>
            </button>
          ))}
        </div>
      )}

      <Dialog open={createOpen} onOpenChange={(open) => !open && setCreateOpen(false)}>
        <DialogContent className="flex max-h-[min(90vh,720px)] flex-col gap-0 overflow-hidden p-0 sm:max-w-lg">
          <DialogHeader className="shrink-0 space-y-1.5 px-6 pt-6 pb-3">
            <DialogTitle>New webhook</DialogTitle>
            <DialogDescription>
              Send a signed update to this address when the events you choose happen.
            </DialogDescription>
          </DialogHeader>
          <div className="min-h-0 flex-1 overflow-y-auto px-6 py-1">
            <EndpointFormFields
              form={createForm}
              setForm={setCreateForm}
              projects={projects}
              projectLocked={false}
              eventTypes={eventTypes}
            />
          </div>
          <DialogFooter className="shrink-0 border-t px-6 py-4">
            <Button variant="outline" onClick={() => setCreateOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={() => void submitCreate()}
              disabled={
                saving ||
                createForm.projectId == null ||
                createForm.name.trim() === '' ||
                createForm.url.trim() === '' ||
                createForm.eventType === '' ||
                (formNeedsFlowChoice(createForm, eventTypes) &&
                  !createForm.allFlows &&
                  createForm.flowIds.length === 0)
              }
            >
              {saving ? 'Creating…' : 'Create webhook'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {reveal != null && (
        <SecretRevealDialog
          orgId={organizationId}
          endpoint={reveal.endpoint}
          secret={reveal.secret}
          onClose={() => {
            setReveal(null)
            void reload()
          }}
          onEndpointUpdated={updateEndpointInList}
        />
      )}

      {detail != null && !editOpen && reveal == null && (
        <Dialog open onOpenChange={(open) => !open && setDetail(null)}>
          <DialogContent className="flex max-h-[min(90vh,720px)] flex-col gap-0 overflow-hidden p-0 sm:max-w-2xl">
            <DialogHeader className="shrink-0 space-y-1.5 px-6 pt-6 pb-3">
              <DialogTitle>{detail.name}</DialogTitle>
              <DialogDescription>
                {detail.project_name ?? 'Project'} · {detail.destination_host} ·{' '}
                {STATUS_LABEL[detail.status] ?? detail.status}
              </DialogDescription>
            </DialogHeader>
            <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-6 pb-6">
              {detail.status === 'paused' && (
                <Alert variant="destructive">
                  <AlertCircle className="h-4 w-4" aria-hidden />
                  <AlertDescription>
                    This webhook is paused because updates could not be delivered for a
                    full day. Fix the destination, send a test, then resume it. Missed
                    updates can be recovered from the project event feed.
                  </AlertDescription>
                </Alert>
              )}
              <div className="space-y-1 text-sm text-muted-foreground">
                <div>
                  Sends updates when {eventTypeLabel(detail.event_types[0] ?? '').toLowerCase()}.
                </div>
                <div>
                  {detail.all_flows
                    ? 'Watching all flows in this project.'
                    : detail.flows.length > 0
                      ? `Watching ${detail.flows
                          .map((flow) => flow.flow_name ?? flow.flow_id)
                          .join(', ')}.`
                      : 'Watching the whole project.'}
                  {detail.outcomes != null &&
                    ` Run updates only when ${detail.outcomes
                      .map(
                        (o) =>
                          OUTCOME_OPTIONS.find((opt) => opt.value === o)?.label.toLowerCase() ?? o,
                      )
                      .join(', ')}.`}
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  disabled={busyAction != null}
                  onClick={() =>
                    void runAction('test', async () => {
                      const response = await testOrganizationWebhookEndpoint(
                        organizationId,
                        detail.id,
                      )
                      updateEndpointInList(response.endpoint)
                      showMessage(
                        response.result.ok
                          ? 'Test delivery received.'
                          : response.result.failure_summary ??
                              'The destination did not accept the test delivery.',
                        { title: response.result.ok ? 'Test succeeded' : 'Test failed' },
                      )
                    })
                  }
                >
                  {busyAction === 'test' ? 'Sending…' : 'Send test'}
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={busyAction != null}
                  onClick={() => {
                    setEditForm({
                      projectId: detail.project_id,
                      name: detail.name,
                      url: '',
                      eventType: detail.event_types[0] ?? RUN_COMPLETED_TYPE,
                      allFlows: detail.all_flows,
                      flowIds: detail.flows.map((flow) => flow.flow_id),
                      outcomes: detail.outcomes ?? [],
                    })
                    setEditOpen(true)
                  }}
                >
                  Edit
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={busyAction != null}
                  onClick={() =>
                    void runAction('rotate', async () => {
                      const ok = await showConfirm(
                        'The current secret stops working and the receiving application must be updated. A new test delivery is required before updates resume.',
                        { title: 'Get a new signing secret?' },
                      )
                      if (!ok) return
                      const rotated = await rotateOrganizationWebhookSecret(
                        organizationId,
                        detail.id,
                      )
                      updateEndpointInList(rotated.endpoint)
                      setDetail(null)
                      setReveal({ endpoint: rotated.endpoint, secret: rotated.signing_secret })
                    })
                  }
                >
                  New secret
                </Button>
                {detail.status === 'disabled' || detail.status === 'paused' ? (
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={busyAction != null}
                    onClick={() =>
                      void runAction('activate', async () => {
                        updateEndpointInList(
                          await activateOrganizationWebhookEndpoint(organizationId, detail.id),
                        )
                      })
                    }
                  >
                    Resume
                  </Button>
                ) : (
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={busyAction != null}
                    onClick={() =>
                      void runAction('disable', async () => {
                        updateEndpointInList(
                          await disableOrganizationWebhookEndpoint(organizationId, detail.id),
                        )
                      })
                    }
                  >
                    Turn off
                  </Button>
                )}
                <Button
                  size="sm"
                  variant="destructive"
                  disabled={busyAction != null}
                  onClick={() =>
                    void runAction('delete', async () => {
                      const ok = await showConfirm(
                        `Delete “${detail.name}”? The receiving application will stop getting updates.`,
                        { title: 'Delete webhook?' },
                      )
                      if (!ok) return
                      await deleteOrganizationWebhookEndpoint(organizationId, detail.id)
                      setEndpoints((prev) => prev.filter((row) => row.id !== detail.id))
                      setDetail(null)
                    })
                  }
                >
                  Delete
                </Button>
              </div>
              <div className="space-y-2">
                <Label>Recent deliveries</Label>
                <DeliveryHistory orgId={organizationId} endpoint={detail} />
              </div>
            </div>
          </DialogContent>
        </Dialog>
      )}

      {detail != null && editOpen && (
        <Dialog open onOpenChange={(open) => !open && setEditOpen(false)}>
          <DialogContent className="flex max-h-[min(90vh,720px)] flex-col gap-0 overflow-hidden p-0 sm:max-w-lg">
            <DialogHeader className="shrink-0 space-y-1.5 px-6 pt-6 pb-3">
              <DialogTitle>Edit webhook</DialogTitle>
              <DialogDescription>
                Changing the destination URL requires a new successful test delivery.
              </DialogDescription>
            </DialogHeader>
            <div className="min-h-0 flex-1 space-y-2 overflow-y-auto px-6 py-1">
              <EndpointFormFields
                form={editForm}
                setForm={setEditForm}
                projects={projects}
                projectLocked
                eventTypes={eventTypes}
              />
              <p className="text-xs text-muted-foreground">
                Leave the destination URL blank to keep the current one (
                {detail.destination_host}).
              </p>
            </div>
            <DialogFooter className="shrink-0 border-t px-6 py-4">
              <Button variant="outline" onClick={() => setEditOpen(false)}>
                Cancel
              </Button>
              <Button
                onClick={() => void submitEdit()}
                disabled={
                  saving ||
                  editForm.name.trim() === '' ||
                  editForm.eventType === '' ||
                  (formNeedsFlowChoice(editForm, eventTypes) &&
                    !editForm.allFlows &&
                    editForm.flowIds.length === 0)
                }
              >
                {saving ? 'Saving…' : 'Save changes'}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </div>
  )
}
