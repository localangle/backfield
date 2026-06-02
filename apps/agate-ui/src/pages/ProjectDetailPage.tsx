import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type KeyboardEvent,
} from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { PageBreadcrumbs } from '@/components/PageBreadcrumbs'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import ProjectSettings, { type ProjectSettingsHandle } from '@/components/ProjectSettings'
import ProjectDetailFlowsTab from '@/components/project/ProjectDetailFlowsTab'
import ProjectDetailRunsTab, {
  type ProjectDetailRunsTabHandle,
} from '@/components/project/ProjectDetailRunsTab'
import ProjectDetailModelsTab from '@/components/project/ProjectDetailModelsTab'
import ProjectDetailIntegrationsTab from '@/components/project/ProjectDetailIntegrationsTab'
import {
  getProjectBySlug,
  getProjectStatsBySlug,
  getProjectEstimatedAiCost,
  updateProject,
  type Project,
  type ProjectStats,
  type ProjectEstimatedAiCost,
} from '@/lib/api'
import { formatDurationMs } from '@/lib/formatDuration'
import { useAuth } from '@/lib/auth'
import { listMyWorkspaces, type WorkspaceWithProjects } from '@/lib/core-api'
import { Loader2, Pencil, Plus, RefreshCw, Check, X } from 'lucide-react'

function formatCurrencySummary(
  value: string | number | null | undefined,
  currency: string,
): string {
  const amount = Number(value)
  const formatter = new Intl.NumberFormat(undefined, {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })

  if (!Number.isFinite(amount)) return '—'
  if (amount <= 0) return formatter.format(0)
  if (amount < 0.01) return `< ${formatter.format(0.01)}`

  const truncated = Math.trunc(amount * 100) / 100
  return formatter.format(truncated)
}

export default function ProjectDetailPage() {
  const navigate = useNavigate()
  const { organizationId, isOrgAdmin } = useAuth()
  const { projectSlug: projectSlugParam } = useParams<{ projectSlug: string }>()
  const slug = projectSlugParam ? decodeURIComponent(projectSlugParam) : ''
  const [project, setProject] = useState<Project | null>(null)
  const [stats, setStats] = useState<ProjectStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [editingName, setEditingName] = useState(false)
  const [nameDraft, setNameDraft] = useState('')
  const [savingName, setSavingName] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const [workspaceTab, setWorkspaceTab] = useState('flows')
  const runsTabRef = useRef<ProjectDetailRunsTabHandle>(null)
  const [runsRefreshBusy, setRunsRefreshBusy] = useState(false)
  const keysSettingsRef = useRef<ProjectSettingsHandle>(null)
  const workspaceSectionRef = useRef<HTMLDivElement>(null)
  const workspaceTabPanelRef = useRef<HTMLDivElement>(null)
  /** Workspace section offset from top of <main> (px); preserved across tab switches. */
  const workspaceScrollAnchorRef = useRef<number | null>(null)
  /** Previous tab panel height (px); prevents collapse to a short loading state on switch. */
  const workspaceTabPanelMinHeightRef = useRef<number | null>(null)
  const [aiCost, setAiCost] = useState<ProjectEstimatedAiCost | null>(null)
  const [projectWorkspace, setProjectWorkspace] = useState<WorkspaceWithProjects | null>(null)
  const reload = useCallback(async () => {
    if (!slug) return
    try {
      setError(null)
      const [p, s] = await Promise.all([getProjectBySlug(slug), getProjectStatsBySlug(slug)])
      setProject(p)
      setStats(s)
      setNameDraft(p.name)
    } catch (e) {
      console.error(e)
      setError('Failed to load project')
      setProject(null)
      setStats(null)
    }
  }, [slug])

  useEffect(() => {
    if (!slug) {
      setLoading(false)
      setError('Invalid project')
      return
    }
    let cancelled = false
    ;(async () => {
      setLoading(true)
      try {
        await reload()
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [slug, reload])

  const captureWorkspaceScrollAnchor = useCallback(() => {
    const section = workspaceSectionRef.current
    const main = section?.closest('main')
    const panel = workspaceTabPanelRef.current
    if (!(section instanceof HTMLElement) || !(main instanceof HTMLElement)) return
    workspaceScrollAnchorRef.current =
      section.getBoundingClientRect().top - main.getBoundingClientRect().top
    if (panel instanceof HTMLElement) {
      const panelHeight = panel.getBoundingClientRect().height
      if (panelHeight > 0) {
        workspaceTabPanelMinHeightRef.current = panelHeight
      }
    }
  }, [])

  const handleWorkspaceTabChange = useCallback((value: string) => {
    setWorkspaceTab(value)
  }, [])

  const handleWorkspaceTabsPointerDownCapture = useCallback(() => {
    captureWorkspaceScrollAnchor()
  }, [captureWorkspaceScrollAnchor])

  const handleWorkspaceTabsKeyDownCapture = useCallback(
    (event: KeyboardEvent) => {
      const { key } = event
      if (
        key === 'ArrowLeft' ||
        key === 'ArrowRight' ||
        key === 'Home' ||
        key === 'End'
      ) {
        captureWorkspaceScrollAnchor()
      }
    },
    [captureWorkspaceScrollAnchor],
  )

  /**
   * Keep the workspace block anchored in the viewport when tab content height changes.
   * Models stays stable because it always mounts tall inline settings; other tabs briefly
   * collapse to a short loading state unless we hold the previous panel min-height.
   */
  useLayoutEffect(() => {
    const targetOffset = workspaceScrollAnchorRef.current
    if (targetOffset == null) return

    const section = workspaceSectionRef.current
    const main = section?.closest('main')
    const panel = workspaceTabPanelRef.current
    if (
      !(section instanceof HTMLElement) ||
      !(main instanceof HTMLElement) ||
      !(panel instanceof HTMLElement)
    ) {
      return
    }

    const minHeight = workspaceTabPanelMinHeightRef.current
    if (minHeight != null && minHeight > 0) {
      panel.style.minHeight = `${Math.ceil(minHeight)}px`
    }

    const alignWorkspaceSection = () => {
      const anchor = workspaceScrollAnchorRef.current
      if (anchor == null) return
      const currentOffset =
        section.getBoundingClientRect().top - main.getBoundingClientRect().top
      const delta = currentOffset - anchor
      if (Math.abs(delta) > 1) {
        main.scrollTop += delta
      }
    }

    const releasePanelMinHeight = () => {
      panel.style.minHeight = ''
      workspaceTabPanelMinHeightRef.current = null
      alignWorkspaceSection()
    }

    alignWorkspaceSection()

    let resizeDebounce = 0
    const resizeObserver = new ResizeObserver(() => {
      alignWorkspaceSection()
      window.clearTimeout(resizeDebounce)
      resizeDebounce = window.setTimeout(releasePanelMinHeight, 120)
    })
    resizeObserver.observe(panel)

    let rafInner = 0
    const rafOuter = requestAnimationFrame(() => {
      alignWorkspaceSection()
      rafInner = requestAnimationFrame(alignWorkspaceSection)
    })

    resizeDebounce = window.setTimeout(releasePanelMinHeight, 120)

    return () => {
      cancelAnimationFrame(rafOuter)
      cancelAnimationFrame(rafInner)
      window.clearTimeout(resizeDebounce)
      resizeObserver.disconnect()
      panel.style.minHeight = ''
    }
  }, [workspaceTab])

  useEffect(() => {
    if (!project?.id) {
      setAiCost(null)
      return
    }
    let cancelled = false
    ;(async () => {
      try {
        const c = await getProjectEstimatedAiCost(project.id)
        if (!cancelled) setAiCost(c)
      } catch {
        if (!cancelled) setAiCost(null)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [project?.id])

  useEffect(() => {
    if (project?.workspace_id == null) {
      setProjectWorkspace(null)
      return
    }
    let cancelled = false
    ;(async () => {
      try {
        const rows = await listMyWorkspaces()
        if (cancelled) return
        setProjectWorkspace(rows.find((row) => row.id === project.workspace_id) ?? null)
      } catch {
        if (!cancelled) setProjectWorkspace(null)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [project?.workspace_id])

  useEffect(() => {
    if (editingName) inputRef.current?.focus()
  }, [editingName])

  const cancelNameEdit = () => {
    setNameDraft(project?.name ?? '')
    setEditingName(false)
  }

  const saveName = async () => {
    if (!project) return
    const next = nameDraft.trim()
    if (!next || next === project.name) {
      cancelNameEdit()
      return
    }
    try {
      setSavingName(true)
      await updateProject(project.id, { name: next })
      setEditingName(false)
      await reload()
      window.dispatchEvent(new CustomEvent('agate:projects-changed'))
    } catch (e) {
      console.error(e)
    } finally {
      setSavingName(false)
    }
  }

  if (!slug) {
    return <p className="text-muted-foreground">Invalid project.</p>
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (error || !project || !stats) {
    return <p className="text-muted-foreground">{error || 'Project not found.'}</p>
  }

  return (
    <div className="w-full max-w-none min-w-0 space-y-10">
      <div className="space-y-2">
        <PageBreadcrumbs
          items={[
            { label: 'Workspaces', to: '/' },
            ...(projectWorkspace
              ? [
                  {
                    label: projectWorkspace.name,
                    to: `/workspace/${encodeURIComponent(projectWorkspace.slug)}`,
                  },
                ]
              : []),
            { label: project.name },
          ]}
        />
        <div className="min-h-[2.5rem]">
          {editingName ? (
            <div className="flex w-full min-w-0 max-w-full flex-nowrap items-center gap-2">
              <Input
                ref={inputRef}
                value={nameDraft}
                onChange={(e) => setNameDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') void saveName()
                  if (e.key === 'Escape') cancelNameEdit()
                }}
                disabled={savingName}
                className="min-w-0 flex-1 max-w-xl text-3xl font-bold h-auto py-2 px-3"
              />
              <Button
                type="button"
                size="icon"
                variant="default"
                className="shrink-0"
                disabled={savingName || !nameDraft.trim()}
                onClick={() => void saveName()}
                aria-label="Save name"
              >
                <Check className="h-4 w-4" />
              </Button>
              <Button
                type="button"
                size="icon"
                variant="outline"
                className="shrink-0"
                disabled={savingName}
                onClick={cancelNameEdit}
                aria-label="Cancel"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          ) : (
            <div className="inline-flex max-w-full items-center gap-2">
              <h1 className="inline-block min-w-0 max-w-[min(100%,42rem)] truncate text-3xl font-bold">
                {project.name}
              </h1>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="shrink-0 text-muted-foreground hover:text-foreground"
                onClick={() => {
                  setNameDraft(project.name)
                  setEditingName(true)
                }}
                aria-label="Edit project name"
              >
                <Pencil className="h-5 w-5" />
              </Button>
            </div>
          )}
        </div>
      </div>

      <div className="w-full min-w-0">
        <h2 className="text-lg font-semibold mb-4">Overview</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 w-full">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">Runs</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex items-baseline justify-between gap-4">
                <span className="text-sm text-muted-foreground inline-flex items-center gap-2">
                  <span aria-hidden="true">🟢</span>
                  Completed
                </span>
                <span className="text-2xl font-semibold tabular-nums">{stats.runs_succeeded}</span>
              </div>
              <div className="flex items-baseline justify-between gap-4">
                <span className="text-sm text-muted-foreground inline-flex items-center gap-2">
                  <span aria-hidden="true">🟡</span>
                  In progress
                </span>
                <span className="text-2xl font-semibold tabular-nums">{stats.runs_in_progress}</span>
              </div>
              <div className="flex items-baseline justify-between gap-4">
                <span className="text-sm text-muted-foreground inline-flex items-center gap-2">
                  <span aria-hidden="true">🔴</span>
                  Stopped
                </span>
                <span className="text-2xl font-semibold tabular-nums">{stats.runs_failed}</span>
              </div>
              <p className="text-xs text-muted-foreground pt-1 border-t border-border">
                Stopped includes runs that ended with an error or were cancelled.
              </p>
            </CardContent>
          </Card>
          {aiCost ? (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">
                  Total estimated AI usage cost
                </CardTitle>
              </CardHeader>
              <CardContent>
                {aiCost.attempt_count === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    No tracked model usage for this project yet.
                  </p>
                ) : (
                  <>
                    <p className="text-3xl font-semibold tabular-nums">
                      {formatCurrencySummary(aiCost.estimated_total, aiCost.currency || 'USD')}
                      {aiCost.incomplete_estimate ? (
                        <span
                          className="text-amber-700 dark:text-amber-400 ml-1"
                          title="Some usage data was missing"
                        >
                          *
                        </span>
                      ) : null}
                    </p>
                    {aiCost.model_breakdown.length > 0 ? (
                      <div className="mt-4 border-t border-border pt-3">
                        <p className="text-xs text-muted-foreground">Top models</p>
                        <div className="mt-2 space-y-2">
                          {aiCost.model_breakdown.slice(0, 3).map((model) => (
                            <div
                              key={model.provider_model_id}
                              className="flex items-center justify-between gap-3 text-sm"
                            >
                              <span
                                className="min-w-0 truncate text-muted-foreground"
                                title={model.provider_model_id}
                              >
                                {model.provider_model_id}
                              </span>
                              <span className="shrink-0 font-medium tabular-nums">
                                {formatCurrencySummary(
                                  model.estimated_total,
                                  aiCost.currency || 'USD',
                                )}
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    ) : null}
                  </>
                )}
              </CardContent>
            </Card>
          ) : null}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Median cost per run
              </CardTitle>
            </CardHeader>
            <CardContent>
              {stats.runs_succeeded > 0 &&
              stats.median_estimated_ai_cost_per_run != null &&
              stats.median_estimated_ai_cost_currency ? (
                <>
                  <p className="text-3xl font-semibold tabular-nums">
                    {formatCurrencySummary(
                      stats.median_estimated_ai_cost_per_run,
                      stats.median_estimated_ai_cost_currency || 'USD',
                    )}
                    {stats.median_estimated_ai_cost_incomplete ? (
                      <span
                        className="text-amber-700 dark:text-amber-400 ml-1"
                        title="Some usage data was missing"
                      >
                        *
                      </span>
                    ) : null}
                  </p>
                  <p className="text-xs text-muted-foreground mt-1">Among completed runs</p>
                </>
              ) : (
                <>
                  <p className="text-3xl font-semibold tabular-nums text-muted-foreground">—</p>
                  <p className="text-xs text-muted-foreground mt-1">No completed runs yet</p>
                </>
              )}
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Median time per run
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-3xl font-semibold tabular-nums">
                {formatDurationMs(stats.median_duration_ms_per_run)}
              </p>
              <p className="text-xs text-muted-foreground mt-1">
                Wall time per completed run
              </p>
            </CardContent>
          </Card>
        </div>
      </div>

      <div ref={workspaceSectionRef} className="w-full min-w-0">
        <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between sm:gap-4">
          <div className="min-w-0 flex-1">
            <h2 className="text-lg font-semibold">Project workspace</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Flows, runs, integrations and API keys for this project.
            </p>
          </div>
          <div className="flex flex-shrink-0 flex-wrap items-center gap-2 sm:justify-end">
            {workspaceTab === 'flows' ? (
              <Button
                type="button"
                onClick={() =>
                  navigate(`/flow/new?project=${encodeURIComponent(slug)}`)
                }
              >
                <Plus className="h-4 w-4 mr-2" />
                New flow
              </Button>
            ) : null}
            {workspaceTab === 'runs' ? (
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={runsRefreshBusy}
                onClick={() => {
                  void (async () => {
                    setRunsRefreshBusy(true)
                    try {
                      await runsTabRef.current?.refresh()
                    } finally {
                      setRunsRefreshBusy(false)
                    }
                  })()
                }}
              >
                <RefreshCw
                  className={`mr-2 h-4 w-4 ${runsRefreshBusy ? 'animate-spin' : ''}`}
                />
                Refresh
              </Button>
            ) : null}
            {workspaceTab === 'keys' ? (
              <Button
                type="button"
                size="sm"
                onClick={() => keysSettingsRef.current?.openAccessKeyCreate?.()}
              >
                <Plus className="h-4 w-4 mr-2" />
                New access key
              </Button>
            ) : null}
          </div>
        </div>
        <Tabs
          value={workspaceTab}
          onValueChange={handleWorkspaceTabChange}
          onPointerDownCapture={handleWorkspaceTabsPointerDownCapture}
          onKeyDownCapture={handleWorkspaceTabsKeyDownCapture}
          className="w-full min-w-0"
        >
          <TabsList className="grid w-full max-w-none grid-cols-2 gap-1 h-auto p-1 sm:grid-cols-3 lg:grid-cols-5">
            <TabsTrigger value="flows" className="w-full">
              Flows
            </TabsTrigger>
            <TabsTrigger value="runs" className="w-full">
              Runs
            </TabsTrigger>
            <TabsTrigger value="models" className="w-full">
              Models
            </TabsTrigger>
            <TabsTrigger value="integrations" className="w-full">
              Integrations
            </TabsTrigger>
            <TabsTrigger
              value="keys"
              className="w-full col-span-2 sm:col-span-1 lg:col-span-1"
            >
              API
            </TabsTrigger>
          </TabsList>
          <div
            ref={workspaceTabPanelRef}
            className="mt-6 w-full min-w-0 [overflow-anchor:none]"
            role="tabpanel"
          >
            {workspaceTab === 'flows' ? (
              <ProjectDetailFlowsTab
                projectId={project.id}
                projectSlug={slug}
                onDataChanged={() => void reload()}
              />
            ) : null}
            {workspaceTab === 'runs' ? (
              <ProjectDetailRunsTab
                ref={runsTabRef}
                projectId={project.id}
                onDataChanged={() => void reload()}
              />
            ) : null}
            {workspaceTab === 'models' ? (
              <div className="w-full min-w-0 space-y-10">
                <ProjectDetailModelsTab projectId={project.id} />
                <ProjectSettings
                  project={project}
                  open={true}
                  onOpenChange={() => {}}
                  variant="inline"
                  inlineScope="system"
                  onRemoteUpdated={reload}
                />
              </div>
            ) : null}
            {workspaceTab === 'integrations' ? (
              <ProjectDetailIntegrationsTab
                projectId={project.id}
                organizationId={organizationId}
                isOrgAdmin={isOrgAdmin}
              />
            ) : null}
            {workspaceTab === 'keys' ? (
              <ProjectSettings
                ref={keysSettingsRef}
                project={project}
                open={true}
                onOpenChange={() => {}}
                variant="inline"
                inlineScope="keys"
                primaryActionsInToolbar
                onRemoteUpdated={reload}
              />
            ) : null}
          </div>
        </Tabs>
      </div>
    </div>
  )
}
