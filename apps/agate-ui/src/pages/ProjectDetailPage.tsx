import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import ProjectSettings, { type ProjectSettingsHandle } from '@/components/ProjectSettings'
import ProjectDetailFlowsTab from '@/components/project/ProjectDetailFlowsTab'
import ProjectDetailRunsTab, {
  type ProjectDetailRunsTabHandle,
} from '@/components/project/ProjectDetailRunsTab'
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
import { Edit, Loader2, Pencil, Plus, RefreshCw, Check, X } from 'lucide-react'

export default function ProjectDetailPage() {
  const navigate = useNavigate()
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
  const systemSettingsRef = useRef<ProjectSettingsHandle>(null)
  const credentialsSettingsRef = useRef<ProjectSettingsHandle>(null)
  const [aiCost, setAiCost] = useState<ProjectEstimatedAiCost | null>(null)

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

      <div className="w-full min-w-0">
        <h2 className="text-lg font-semibold mb-4">Overview</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 w-full">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">Runs</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-3xl font-semibold tabular-nums">{stats.total_runs}</p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Articles processed
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-3xl font-semibold tabular-nums">{stats.articles_processed}</p>
              <p className="text-xs text-muted-foreground mt-1">
                Successful runs (one unit per run in Agate today)
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Avg time per run
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-3xl font-semibold tabular-nums">
                {formatDurationMs(stats.avg_duration_ms_per_run)}
              </p>
              <p className="text-xs text-muted-foreground mt-1">Finished runs only</p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Avg time per item
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-3xl font-semibold tabular-nums">
                {formatDurationMs(stats.avg_duration_ms_per_item)}
              </p>
              <p className="text-xs text-muted-foreground mt-1">Per successful run</p>
            </CardContent>
          </Card>
        </div>
        {aiCost ? (
          <Card className="mt-4">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Estimated AI usage cost
              </CardTitle>
            </CardHeader>
            <CardContent>
              {aiCost.attempt_count === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No tracked model usage for this project yet.
                </p>
              ) : (
                <>
                  <p className="text-2xl font-semibold tabular-nums">
                    {Number(aiCost.estimated_total).toLocaleString(undefined, {
                      style: 'currency',
                      currency: aiCost.currency || 'USD',
                      minimumFractionDigits: 2,
                      maximumFractionDigits: 6,
                    })}
                  </p>
                  {aiCost.incomplete_estimate ? (
                    <p className="text-xs text-amber-700 dark:text-amber-400 mt-2">
                      Some usage data was missing, so this total may be incomplete.
                    </p>
                  ) : null}
                </>
              )}
            </CardContent>
          </Card>
        ) : null}
      </div>

      <div className="w-full min-w-0">
        <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between sm:gap-4">
          <div className="min-w-0 flex-1">
            <h2 className="text-lg font-semibold">Project workspace</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Flows, runs, defaults, and API credentials for this project.
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
            {workspaceTab === 'settings' ? (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => systemSettingsRef.current?.openSystemPromptEdit?.()}
              >
                <Edit className="h-4 w-4 mr-2" />
                Edit system prompt
              </Button>
            ) : null}
            {workspaceTab === 'credentials' ? (
              <>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => credentialsSettingsRef.current?.openAccessKeyCreate?.()}
                >
                  <Plus className="h-4 w-4 mr-2" />
                  New access key
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => credentialsSettingsRef.current?.openAddProviderSecret?.()}
                >
                  <Plus className="h-4 w-4 mr-2" />
                  Add provider secret
                </Button>
              </>
            ) : null}
          </div>
        </div>
        <Tabs
          value={workspaceTab}
          onValueChange={setWorkspaceTab}
          className="w-full min-w-0"
        >
          <TabsList className="grid w-full max-w-none grid-cols-2 gap-1 h-auto p-1 sm:grid-cols-4">
            <TabsTrigger value="flows" className="w-full">
              Flows
            </TabsTrigger>
            <TabsTrigger value="runs" className="w-full">
              Runs
            </TabsTrigger>
            <TabsTrigger value="settings" className="w-full">
              Settings
            </TabsTrigger>
            <TabsTrigger value="credentials" className="w-full">
              Credentials
            </TabsTrigger>
          </TabsList>
          <TabsContent value="flows" className="mt-6 w-full min-w-0 outline-none">
            <ProjectDetailFlowsTab
              projectId={project.id}
              projectSlug={slug}
              onDataChanged={() => void reload()}
            />
          </TabsContent>
          <TabsContent value="runs" className="mt-6 w-full min-w-0 outline-none">
            <ProjectDetailRunsTab
              ref={runsTabRef}
              projectId={project.id}
              onDataChanged={() => void reload()}
            />
          </TabsContent>
          <TabsContent value="settings" className="mt-6 w-full min-w-0 outline-none">
            <ProjectSettings
              ref={systemSettingsRef}
              project={project}
              open={true}
              onOpenChange={() => {}}
              variant="inline"
              inlineScope="system"
              primaryActionsInToolbar
              onRemoteUpdated={reload}
            />
          </TabsContent>
          <TabsContent value="credentials" className="mt-6 w-full min-w-0 outline-none">
            <ProjectSettings
              ref={credentialsSettingsRef}
              project={project}
              open={true}
              onOpenChange={() => {}}
              variant="inline"
              inlineScope="credentials"
              primaryActionsInToolbar
              onRemoteUpdated={reload}
            />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  )
}
