import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAppMessage } from '@/components/AppMessageProvider'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { listRuns, listGraphs, listProjects, cancelRun, type Run, type Graph, type Project } from '@/lib/api'
import { formatRunEstimatedAiCost } from '@/lib/formatRunEstimatedCost'
import { formatDate } from '@/lib/utils'
import { Loader2, CheckCircle, XCircle, Clock, ArrowRight, RefreshCw, Building2, AlertTriangle, StopCircle, ChevronLeft, ChevronRight } from 'lucide-react'

const RUNS_PER_PAGE = 50

export default function RunsList() {
  const { showConfirm, showError } = useAppMessage()
  const [runs, setRuns] = useState<Run[]>([])
  const [allRuns, setAllRuns] = useState<Run[]>([]) // Store all fetched runs
  const [graphs, setGraphs] = useState<Graph[]>([])
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedFlow, setSelectedFlow] = useState<string>('all')
  const [selectedStatus, setSelectedStatus] = useState<string>('all')
  const [selectedProject, setSelectedProject] = useState<string>('all')
  const [refreshing, setRefreshing] = useState(false)
  const [cancellingRuns, setCancellingRuns] = useState<Set<string>>(new Set())
  const [currentPage, setCurrentPage] = useState(1)
  const [hasMore, setHasMore] = useState(true)
  const navigate = useNavigate()

  useEffect(() => {
    loadData()
  }, [])

  // Reset to page 1 when filters change
  useEffect(() => {
    setCurrentPage(1)
  }, [selectedFlow, selectedStatus, selectedProject])

  // Auto-refresh for running flows (but only update if data changed)
  useEffect(() => {
    const hasRunningFlows = allRuns.some(run => run.status === 'pending' || run.status === 'running')
    if (hasRunningFlows) {
      // Add random jitter to prevent thundering herd
      const baseInterval = 10000 // 10 seconds base interval
      const jitter = Math.random() * 2000 // Random 0-2 second jitter
      const pollInterval = baseInterval + jitter
      
      const interval = setInterval(async () => {
        try {
          // Fetch current page
          const offset = (currentPage - 1) * RUNS_PER_PAGE
          const newRuns = await listRuns(RUNS_PER_PAGE, offset)
          // Only update state if data has actually changed
          if (JSON.stringify(newRuns) !== JSON.stringify(allRuns)) {
            setAllRuns(newRuns)
            setHasMore(newRuns.length === RUNS_PER_PAGE)
          }
        } catch (error) {
          console.error('Failed to refresh runs:', error)
        }
      }, pollInterval)
      return () => clearInterval(interval)
    }
    // Return empty cleanup function if no interval was created
    return () => {}
  }, [allRuns, currentPage])

  async function loadData() {
    try {
      setLoading(true)
      await Promise.all([loadRuns(), loadGraphs(), loadProjects()])
    } catch (error) {
      console.error('Failed to load data:', error)
    } finally {
      setLoading(false)
    }
  }

  async function loadRuns() {
    try {
      const offset = (currentPage - 1) * RUNS_PER_PAGE
      const data = await listRuns(RUNS_PER_PAGE, offset)
      setAllRuns(data)
      setHasMore(data.length === RUNS_PER_PAGE)
    } catch (error) {
      console.error('Failed to load runs:', error)
    }
  }

  async function loadGraphs() {
    try {
      const data = await listGraphs()
      setGraphs(data)
    } catch (error) {
      console.error('Failed to load graphs:', error)
    }
  }

  async function loadProjects() {
    try {
      const data = await listProjects()
      setProjects(data)
    } catch (error) {
      console.error('Failed to load projects:', error)
    }
  }

  async function handleRefresh() {
    setRefreshing(true)
    await loadRuns()
    setRefreshing(false)
  }

  async function handlePageChange(newPage: number) {
    setCurrentPage(newPage)
    setRefreshing(true)
    try {
      const offset = (newPage - 1) * RUNS_PER_PAGE
      const data = await listRuns(RUNS_PER_PAGE, offset)
      setAllRuns(data)
      setHasMore(data.length === RUNS_PER_PAGE)
    } catch (error) {
      console.error('Failed to load runs:', error)
    } finally {
      setRefreshing(false)
    }
  }

  async function handleCancelRun(runId: string, event: React.MouseEvent) {
    event.stopPropagation()

    const ok = await showConfirm(
      'Are you sure you want to cancel this run? This will stop all pending and running items.',
      {
        title: 'Stop run',
        confirmLabel: 'Stop run',
        destructive: true,
      },
    )
    if (!ok) return

    setCancellingRuns(prev => new Set(prev).add(runId))
    
    try {
      await cancelRun(runId)
      await loadRuns() // Refresh the list
    } catch (error) {
      console.error('Failed to cancel run:', error)
      showError('Failed to cancel run. Please try again.')
    } finally {
      setCancellingRuns(prev => {
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
    const graph = graphs.find(g => g.id === graphId)
    return graph?.name || `Flow ${graphId}`
  }

  const getProjectName = (projectId: number) => {
    const project = projects.find(p => p.id === projectId)
    return project?.name || `Project ${projectId}`
  }

  const getDuration = (run: Run) => {
    if (run.status === 'pending' || run.status === 'running') {
      return 'Running...'
    }
    
    const start = new Date(run.created_at)
    const end = new Date(run.updated_at)
    const duration = end.getTime() - start.getTime()
    
    if (duration < 1000) {
      return '< 1s'
    } else if (duration < 60000) {
      return `${Math.round(duration / 1000)}s`
    } else {
      return `${Math.round(duration / 60000)}m ${Math.round((duration % 60000) / 1000)}s`
    }
  }

  // Filter and sort runs based on selected filters (applied to current page)
  const filteredRuns = allRuns
    .filter(run => {
      const flowMatch = selectedFlow === 'all' || run.graph_id.toString() === selectedFlow
      const statusMatch = selectedStatus === 'all' || run.status === selectedStatus
      const projectMatch = selectedProject === 'all' || run.project_id.toString() === selectedProject
      return flowMatch && statusMatch && projectMatch
    })
    .sort((a, b) => {
      // Sort by status priority first: running at top, then pending
      const statusOrder = { 'running': 0, 'pending': 1, 'completed': 2, 'completed_with_errors': 3 }
      const aOrder = statusOrder[a.status as keyof typeof statusOrder] ?? 4
      const bOrder = statusOrder[b.status as keyof typeof statusOrder] ?? 4
      
      if (aOrder !== bOrder) {
        return aOrder - bOrder
      }
      
      // Then sort by creation date (newest first)
      return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
    })

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Runs</h1>
          <p className="text-muted-foreground mt-1">
            View and manage flow execution history
          </p>
        </div>
        <Button onClick={handleRefresh} disabled={refreshing}>
          <RefreshCw className={`mr-2 h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </div>

      {/* Filters */}
      <div className="flex gap-4">
        <div className="flex flex-col gap-1">
          <label className="text-sm font-medium">Filter by Project</label>
          <Select value={selectedProject} onValueChange={setSelectedProject}>
            <SelectTrigger className="w-[200px]">
              <SelectValue placeholder="All Projects" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Projects</SelectItem>
              {projects.map((project) => (
                <SelectItem key={project.id} value={project.id.toString()}>
                  <div className="flex items-center gap-2">
                    <Building2 className="h-3 w-3" />
                    {project.name}
                  </div>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-sm font-medium">Filter by Flow</label>
          <Select value={selectedFlow} onValueChange={setSelectedFlow}>
            <SelectTrigger className="w-[200px]">
              <SelectValue placeholder="All Flows" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Flows</SelectItem>
              {graphs.map((graph) => (
                <SelectItem key={graph.id} value={graph.id.toString()}>
                  {graph.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        
        <div className="flex flex-col gap-1">
          <label className="text-sm font-medium">Filter by Status</label>
          <Select value={selectedStatus} onValueChange={setSelectedStatus}>
            <SelectTrigger className="w-[200px]">
              <SelectValue placeholder="All Statuses" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Statuses</SelectItem>
              <SelectItem value="pending">Pending</SelectItem>
              <SelectItem value="running">Running</SelectItem>
              <SelectItem value="succeeded">Succeeded</SelectItem>
              <SelectItem value="failed">Failed</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {filteredRuns.length === 0 ? (
        <Card>
          <CardContent className="py-12">
            <div className="text-center">
              <p className="text-muted-foreground mb-4">
                {allRuns.length === 0 
                  ? "No runs yet. Execute a flow to see run history."
                  : "No runs match the current filters."
                }
              </p>
            </div>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="p-0">
            <table className="w-full">
              <thead className="border-b bg-muted/50">
                <tr>
                  <th className="text-left p-4 font-medium">Project</th>
                  <th className="text-left p-4 font-medium">Flow</th>
                  <th className="text-left p-4 font-medium">Status</th>
                  <th className="text-left p-4 font-medium">Created</th>
                  <th className="text-left p-4 font-medium">Estimated cost</th>
                  <th className="text-left p-4 font-medium">Duration</th>
                  <th className="text-right p-4 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredRuns.map((run) => {
                  const costFmt = formatRunEstimatedAiCost(run)
                  return (
                  <tr
                    key={run.id}
                    className="border-b last:border-b-0 hover:bg-muted/[0.07] transition-colors cursor-pointer"
                    onClick={() => navigate(`/runs/${run.id}`)}
                  >
                    <td className="p-4">
                      <div className="flex items-center gap-2">
                        <Building2 className="h-3 w-3 text-muted-foreground" />
                        <span className="text-sm font-medium">{getProjectName(run.project_id)}</span>
                      </div>
                    </td>
                    <td className="p-4">
                      <div className="font-medium">{getGraphName(run.graph_id)}</div>
                    </td>
                    <td className="p-4">
                      <Badge variant="outline" className={getStatusColor(run.status)}>
                        {getStatusIcon(run.status)}
                        <span className="ml-1 capitalize">{run.status.replace(/_/g, ' ')}</span>
                      </Badge>
                      <div className="text-xs text-muted-foreground mt-1">
                        {run.succeeded_items}/{run.total_items} completed
                      </div>
                    </td>
                    <td className="p-4 text-sm text-muted-foreground">
                      {formatDate(run.created_at, { dateStyle: 'medium', timeStyle: 'short' })}
                    </td>
                    <td className="p-4 text-sm text-muted-foreground tabular-nums">
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
                    <td className="p-4 text-sm text-muted-foreground">
                      {getDuration(run)}
                    </td>
                    <td className="p-4 text-right">
                      <div className="flex items-center justify-end gap-2">
                        {(run.status === 'pending' || run.status === 'running') && (
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={(e) => handleCancelRun(run.id, e)}
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
            {/* Pagination Controls */}
            {(hasMore || currentPage > 1) && (
              <div className="flex items-center justify-between p-4 border-t">
                <div className="text-sm text-muted-foreground">
                  Showing {filteredRuns.length > 0 ? (currentPage - 1) * RUNS_PER_PAGE + 1 : 0} to {(currentPage - 1) * RUNS_PER_PAGE + filteredRuns.length} runs
                  {hasMore && ' (more available)'}
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handlePageChange(currentPage - 1)}
                    disabled={currentPage === 1 || refreshing}
                  >
                    <ChevronLeft className="h-4 w-4" />
                    Previous
                  </Button>
                  <div className="text-sm text-muted-foreground">
                    Page {currentPage}
                    {hasMore && '+'}
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handlePageChange(currentPage + 1)}
                    disabled={!hasMore || refreshing}
                  >
                    Next
                    <ChevronRight className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  )
}
