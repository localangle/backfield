import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAppMessage } from '@/components/AppMessageProvider'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { listRuns, listGraphSummaries, cancelRun, type Run, type GraphSummary } from '@/lib/api'
import { formatRunEstimatedAiCost } from '@/lib/formatRunEstimatedCost'
import { formatDate } from '@/lib/utils'
import {
  Loader2,
  CheckCircle,
  Clock,
  ArrowRight,
  AlertTriangle,
  StopCircle,
} from 'lucide-react'

interface ProjectDetailRunsTabProps {
  projectId: number
  onDataChanged?: () => void
}

export type ProjectDetailRunsTabHandle = {
  refresh: () => Promise<void>
}

const RUNS_PAGE_SIZE = 100

const ProjectDetailRunsTab = forwardRef<ProjectDetailRunsTabHandle, ProjectDetailRunsTabProps>(
  function ProjectDetailRunsTab({ projectId, onDataChanged }, ref) {
  const { showConfirm, showError } = useAppMessage()
  const [runs, setRuns] = useState<Run[]>([])
  const [graphs, setGraphs] = useState<GraphSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedFlow, setSelectedFlow] = useState<string>('all')
  const [selectedStatus, setSelectedStatus] = useState<string>('all')
  const [cancellingRuns, setCancellingRuns] = useState<Set<string>>(new Set())
  const navigate = useNavigate()

  const projectGraphs = useMemo(
    () => graphs.filter((g) => g.project_id === projectId),
    [graphs, projectId]
  )

  const loadData = useCallback(async () => {
    try {
      setLoading(true)
      const [runsData, graphsData] = await Promise.all([
        listRuns({
          projectId,
          limit: RUNS_PAGE_SIZE,
          includeResult: false,
          includeGraphSpecSnapshot: false,
        }),
        listGraphSummaries(projectId),
      ])
      setRuns(runsData)
      setGraphs(graphsData)
    } catch (error) {
      console.error('Failed to load runs:', error)
    } finally {
      setLoading(false)
    }
  }, [projectId])

  useEffect(() => {
    void loadData()
  }, [loadData])

  const handleRefresh = useCallback(async () => {
    try {
      const runsData = await listRuns({
        projectId,
        limit: RUNS_PAGE_SIZE,
        includeResult: false,
        includeGraphSpecSnapshot: false,
      })
      setRuns(runsData)
      onDataChanged?.()
    } catch (e) {
      console.error(e)
    }
  }, [projectId, onDataChanged])

  useImperativeHandle(ref, () => ({ refresh: handleRefresh }), [handleRefresh])

  const handleCancelRun = async (runId: string, event: React.MouseEvent) => {
    event.stopPropagation()
    const ok = await showConfirm('Cancel this run? Pending and running work will stop.', {
      title: 'Stop run',
      confirmLabel: 'Stop run',
      destructive: true,
    })
    if (!ok) return
    setCancellingRuns((prev) => new Set(prev).add(runId))
    try {
      await cancelRun(runId)
      const runsData = await listRuns({
        projectId,
        limit: RUNS_PAGE_SIZE,
        includeResult: false,
        includeGraphSpecSnapshot: false,
      })
      setRuns(runsData)
      onDataChanged?.()
    } catch (error) {
      console.error('Failed to cancel run:', error)
      showError('Failed to cancel run.')
    } finally {
      setCancellingRuns((prev) => {
        const next = new Set(prev)
        next.delete(runId)
        return next
      })
    }
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'running':
        return 'bg-yellow-100 text-yellow-800 border-yellow-200'
      case 'completed':
        return 'bg-green-100 text-green-800 border-green-200'
      case 'completed_with_errors':
        return 'bg-orange-100 text-orange-800 border-orange-200'
      case 'pending':
        return 'bg-gray-100 text-gray-800 border-gray-200'
      default:
        return 'bg-gray-100 text-gray-800 border-gray-200'
    }
  }

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'running':
        return <Loader2 className="h-4 w-4 animate-spin" />
      case 'completed':
        return <CheckCircle className="h-4 w-4" />
      case 'completed_with_errors':
        return <AlertTriangle className="h-4 w-4" />
      case 'pending':
        return <Clock className="h-4 w-4" />
      default:
        return <Clock className="h-4 w-4" />
    }
  }

  const getGraphName = (graphId: string) => {
    const graph = graphs.find((g) => g.id === graphId)
    return graph?.name || `Flow ${graphId}`
  }

  const getDuration = (run: Run) => {
    if (run.status === 'pending' || run.status === 'running') return 'Running…'
    const start = new Date(run.created_at).getTime()
    const end = new Date(run.updated_at).getTime()
    const duration = end - start
    if (duration < 1000) return '< 1s'
    if (duration < 60000) return `${Math.round(duration / 1000)}s`
    return `${Math.round(duration / 60000)}m ${Math.round((duration % 60000) / 1000)}s`
  }

  const filteredRuns = useMemo(() => {
    return runs
      .filter((run) => {
        const flowMatch = selectedFlow === 'all' || run.graph_id === selectedFlow
        const statusMatch = selectedStatus === 'all' || run.status === selectedStatus
        return flowMatch && statusMatch
      })
      .sort(
        (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
      )
  }, [runs, selectedFlow, selectedStatus])

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <div className="space-y-4 w-full min-w-0">
      <p className="text-sm text-muted-foreground mb-1">
        Runs for flows in this project.
      </p>

      <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap">
        <div className="flex flex-col gap-1 min-w-0 sm:min-w-[10rem]">
          <label className="text-sm font-medium">Flow</label>
          <Select value={selectedFlow} onValueChange={setSelectedFlow}>
            <SelectTrigger className="w-full sm:w-[200px]">
              <SelectValue placeholder="All flows" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All flows</SelectItem>
              {projectGraphs.map((g) => (
                <SelectItem key={g.id} value={g.id}>
                  {g.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex flex-col gap-1 min-w-0 sm:min-w-[10rem]">
          <label className="text-sm font-medium">Status</label>
          <Select value={selectedStatus} onValueChange={setSelectedStatus}>
            <SelectTrigger className="w-full sm:w-[180px]">
              <SelectValue placeholder="All statuses" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All statuses</SelectItem>
              <SelectItem value="pending">Pending</SelectItem>
              <SelectItem value="running">Running</SelectItem>
              <SelectItem value="completed">Completed</SelectItem>
              <SelectItem value="completed_with_errors">Completed with errors</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {filteredRuns.length === 0 ? (
        <Card>
          <CardContent className="py-12">
            <p className="text-center text-muted-foreground">
              {runs.length === 0
                ? 'No runs yet for this project.'
                : 'No runs match the current filters.'}
            </p>
          </CardContent>
        </Card>
      ) : (
        <Card className="overflow-hidden">
          <CardContent className="p-0">
            <div className="w-full overflow-x-auto">
              <table className="w-full min-w-[640px] text-sm">
                <thead className="border-b bg-muted/50">
                  <tr>
                    <th className="text-left p-3 sm:p-4 font-medium">Flow</th>
                    <th className="text-left p-3 sm:p-4 font-medium">Status</th>
                    <th className="text-left p-3 sm:p-4 font-medium hidden sm:table-cell">Created</th>
                    <th className="text-left p-3 sm:p-4 font-medium hidden sm:table-cell">
                      Estimated cost
                    </th>
                    <th className="text-left p-3 sm:p-4 font-medium hidden md:table-cell">Duration</th>
                    <th className="text-right p-3 sm:p-4 font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredRuns.map((run) => {
                    const costFmt = formatRunEstimatedAiCost(run)
                    return (
                    <tr
                      key={run.id}
                      className="border-b last:border-b-0 hover:bg-muted/[0.07] cursor-pointer transition-colors"
                      onClick={() => navigate(`/runs/${run.id}`)}
                    >
                      <td className="p-3 sm:p-4 align-top">
                        <div className="font-medium">{getGraphName(run.graph_id)}</div>
                      </td>
                      <td className="p-3 sm:p-4 align-top">
                        <Badge variant="outline" className={getStatusColor(run.status)}>
                          {getStatusIcon(run.status)}
                          <span className="ml-1 capitalize">{run.status.replace(/_/g, ' ')}</span>
                        </Badge>
                        <div className="text-xs text-muted-foreground mt-1">
                          {run.succeeded_items}/{run.total_items} completed
                        </div>
                      </td>
                      <td className="p-3 sm:p-4 text-muted-foreground align-top hidden sm:table-cell whitespace-nowrap">
                        {formatDate(run.created_at, { dateStyle: 'medium', timeStyle: 'short' })}
                      </td>
                      <td className="p-3 sm:p-4 text-muted-foreground align-top hidden sm:table-cell whitespace-nowrap tabular-nums">
                        <>
                          {costFmt.display}
                          {costFmt.incomplete ? (
                            <span
                              className="text-amber-700 dark:text-amber-400 ml-0.5"
                              title="Estimate may be incomplete"
                            >
                              *
                            </span>
                          ) : null}
                        </>
                      </td>
                      <td className="p-3 sm:p-4 text-muted-foreground align-top hidden md:table-cell whitespace-nowrap">
                        {getDuration(run)}
                      </td>
                      <td className="p-3 sm:p-4 text-right align-top">
                        <div className="flex items-center justify-end gap-2">
                          {(run.status === 'pending' || run.status === 'running') && (
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={(e) => void handleCancelRun(run.id, e)}
                              disabled={cancellingRuns.has(run.id)}
                              className="text-red-600 hover:text-red-700 hover:bg-red-50"
                            >
                              {cancellingRuns.has(run.id) ? (
                                <Loader2 className="h-4 w-4 animate-spin" />
                              ) : (
                                <StopCircle className="h-4 w-4" />
                              )}
                            </Button>
                          )}
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={(e) => {
                              e.stopPropagation()
                              navigate(`/runs/${run.id}`)
                            }}
                          >
                            View
                            <ArrowRight className="ml-2 h-4 w-4" />
                          </Button>
                        </div>
                      </td>
                    </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
},
)

export default ProjectDetailRunsTab
