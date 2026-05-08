import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useAppMessage } from '@/components/AppMessageProvider'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import {
  getRun,
  getGraph,
  createRun,
  cancelRun,
  rerunProcessedItem,
  getRunEstimatedAiCost,
  type Run,
  type Graph,
  type ProcessedItemSummary,
  type RunEstimatedAiCost,
} from '@/lib/api'
import { formatDateCentral } from '@/lib/utils'
import { getNodeStepDisplayName } from '@/lib/nodeUtils'
import { ArrowLeft, Download, CheckCircle, XCircle, Clock, Loader2, AlertTriangle, FileText, Play, StopCircle, ExternalLink, RotateCcw } from 'lucide-react'
import { Checkbox } from '@/components/ui/checkbox'

export default function RunDetail() {
  const { showConfirm, showError } = useAppMessage()
  const { runId } = useParams<{ runId: string }>()
  const navigate = useNavigate()
  const [run, setRun] = useState<Run | null>(null)
  const [graph, setGraph] = useState<Graph | null>(null)
  const [loading, setLoading] = useState(true)
  const [runningAgain, setRunningAgain] = useState(false)
  const [cancelling, setCancelling] = useState(false)
  const [currentPage, setCurrentPage] = useState(1)
  const itemsPerPage = 100
  const [selectedItems, setSelectedItems] = useState<Set<number>>(new Set())
  const [rerunningItems, setRerunningItems] = useState<Set<number>>(new Set())
  const [aiCost, setAiCost] = useState<RunEstimatedAiCost | null>(null)

  useEffect(() => {
    if (runId) {
      loadRunData()
      setCurrentPage(1) // Reset to first page when run changes
      setSelectedItems(new Set()) // Clear selection when run changes
    }
  }, [runId])

  // Auto-refresh for flows with pending or running status (but only update if data changed)
  useEffect(() => {
    if (run && (run.status === 'pending' || run.status === 'running')) {
      // Add random jitter to prevent thundering herd
      const baseInterval = 5000 // 5 seconds base interval
      const jitter = Math.random() * 1000 // Random 0-1 second jitter
      const pollInterval = baseInterval + jitter
      
      const interval = setInterval(async () => {
        if (!runId) return
        
        try {
          // Only call getRun once, then use the result to get the graph
          const newRun = await getRun(runId)
          const graphData = await getGraph(newRun.graph_id)
          
          // Only update state if data has actually changed
          if (JSON.stringify(newRun) !== JSON.stringify(run)) {
            setRun(newRun)
          }
          if (JSON.stringify(graphData) !== JSON.stringify(graph)) {
            setGraph(graphData)
          }
        } catch (error) {
          console.error('Failed to refresh run:', error)
        }
      }, pollInterval)
      return () => clearInterval(interval)
    }
    // Return empty cleanup function if no interval was created
    return () => {}
  }, [run?.status, runId]) // Only depend on run.status and runId, not the entire run/graph objects

  async function loadRunData() {
    if (!runId) return

    try {
      setLoading(true)
      // Only call getRun once, then use the result to get the graph
      const runData = await getRun(runId)
      const graphData = await getGraph(runData.graph_id)
      setRun(runData)
      setGraph(graphData)
      try {
        const cost = await getRunEstimatedAiCost(runId)
        setAiCost(cost)
      } catch {
        setAiCost(null)
      }
    } catch (error) {
      console.error('Failed to load run data:', error)
    } finally {
      setLoading(false)
    }
  }

  async function handleRunAgain() {
    if (!run || !graph) return

    try {
      setRunningAgain(true)
      // Create a new run with the same graph ID and empty input (input is part of graph spec)
      const newRun = await createRun(run.graph_id, {
        input: {}
      })
      // Navigate to the new run detail page
      navigate(`/runs/${newRun.id}`)
    } catch (error) {
      console.error('Failed to run again:', error)
      // You could add a toast notification here if you have a toast system
    } finally {
      setRunningAgain(false)
    }
  }

  async function handleCancelRun() {
    if (!run || !runId) return

    const ok = await showConfirm(
      'Are you sure you want to cancel this run? This will stop all pending and running items.',
      {
        title: 'Cancel run',
        confirmLabel: 'Cancel run',
        destructive: true,
      },
    )
    if (!ok) return

    try {
      setCancelling(true)
      await cancelRun(runId)
      await loadRunData() // Refresh the run data
    } catch (error) {
      console.error('Failed to cancel run:', error)
      showError('Failed to cancel run. Please try again.')
    } finally {
      setCancelling(false)
    }
  }

  function handleSelectItem(itemId: number, checked: boolean) {
    setSelectedItems(prev => {
      const next = new Set(prev)
      if (checked) {
        next.add(itemId)
      } else {
        next.delete(itemId)
      }
      return next
    })
  }

  function handleSelectAll() {
    if (!run?.items) return
    // Select all items across all pages
    const allItemIds = new Set(run.items.map(item => item.id))
    setSelectedItems(allItemIds)
  }

  function handleDeselectAll() {
    setSelectedItems(new Set())
  }

  function handleSelectFailed() {
    if (!run?.items) return
    const failedItemIds = new Set(
      run.items
        .filter(item => item.status === 'failed' || item.status === 'timed_out')
        .map(item => item.id)
    )
    setSelectedItems(failedItemIds)
  }

  async function handleBulkRerun() {
    if (!runId || selectedItems.size === 0) return

    const ok = await showConfirm(`Are you sure you want to rerun ${selectedItems.size} item(s)?`, {
      title: 'Rerun items',
      confirmLabel: 'Rerun',
    })
    if (!ok) return

    const itemIds = Array.from(selectedItems)
    setRerunningItems(new Set(itemIds))

    try {
      // Rerun all selected items in parallel
      await Promise.all(
        itemIds.map(itemId => rerunProcessedItem(runId, itemId))
      )
      
      // Clear selection and refresh data
      setSelectedItems(new Set())
      await loadRunData()
    } catch (error) {
      console.error('Failed to rerun items:', error)
      showError('Failed to rerun some items. Please check the console for details.')
    } finally {
      setRerunningItems(new Set())
    }
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'running':
        return 'bg-yellow-100 text-yellow-800 border-yellow-200'
      case 'succeeded':
        return 'bg-green-100 text-green-800 border-green-200'
      case 'failed':
        return 'bg-red-100 text-red-800 border-red-200'
      case 'timed_out':
        return 'bg-orange-100 text-orange-800 border-orange-200'
      case 'skipped':
        return 'bg-slate-100 text-slate-700 border-slate-200'
      default:
        return 'bg-gray-100 text-gray-800 border-gray-200'
    }
  }

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'running':
        return <Loader2 className="h-4 w-4 animate-spin" />
      case 'succeeded':
        return <CheckCircle className="h-4 w-4" />
      case 'failed':
        return <XCircle className="h-4 w-4" />
      case 'timed_out':
        return <AlertTriangle className="h-4 w-4" />
      case 'skipped':
        return <AlertTriangle className="h-4 w-4" />
      default:
        return <Clock className="h-4 w-4" />
    }
  }

  const getS3Url = (item: ProcessedItemSummary): string | null => {
    if (item.output_s3_bucket && item.output_s3_key) {
      return `https://${item.output_s3_bucket}.s3.amazonaws.com/${item.output_s3_key}`
    }
    return null
  }

  const formatJson = (data: any) => {
    try {
      return JSON.stringify(data, null, 2)
    } catch {
      return String(data)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (!run) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-center">
          <AlertTriangle className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
          <h2 className="text-xl font-semibold mb-2">Run Not Found</h2>
          <p className="text-muted-foreground mb-4">
            The run you're looking for doesn't exist or has been deleted.
          </p>
          <Button onClick={() => navigate('/')}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back to Home
          </Button>
        </div>
      </div>
    )
  }

  const hasRunningItems = run.pending_items > 0 || run.running_items > 0

  // Check if the flow has an APIInput node (API-triggered flows)
  const hasAPIInput = graph?.spec?.nodes?.some((node: any) => node.type === 'APIInput') || false

  // Pagination calculations
  const totalItems = run.items?.length || 0
  const totalPages = Math.ceil(totalItems / itemsPerPage)
  const startIndex = (currentPage - 1) * itemsPerPage
  const endIndex = startIndex + itemsPerPage
  const paginatedItems = run.items?.slice(startIndex, endIndex) || []

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button variant="ghost" onClick={() => navigate('/')}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back
          </Button>
          <div>
            <h1 className="text-3xl font-bold">Run #{run.id}</h1>
            <p className="text-muted-foreground mt-1">
              {graph?.name || `Flow ${run.graph_id}`}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {(run.status === 'pending' || run.status === 'running') && (
            <Button 
              onClick={handleCancelRun} 
              disabled={cancelling}
              variant="destructive"
              className="flex items-center gap-2"
            >
              {cancelling ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <StopCircle className="h-4 w-4" />
              )}
              {cancelling ? 'Cancelling...' : 'Stop Run'}
            </Button>
          )}
          {hasAPIInput ? (
            <div 
              title="API-triggered flows cannot be run again manually. Use the API endpoint to trigger a new run."
              className="inline-block"
            >
              <Button 
                onClick={handleRunAgain} 
                disabled={true}
                className="flex items-center gap-2"
              >
                <Play className="h-4 w-4" />
                Run Again
              </Button>
            </div>
          ) : (
            <Button 
              onClick={handleRunAgain} 
              disabled={runningAgain || run.status === 'running' || run.status === 'pending'}
              className="flex items-center gap-2"
            >
              {runningAgain ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Play className="h-4 w-4" />
              )}
              {runningAgain ? 'Running...' : 'Run Again'}
            </Button>
          )}
        </div>
      </div>

      {/* Run Summary */}
      <Card>
        <CardHeader>
          <CardTitle>Run Summary</CardTitle>
          <CardDescription>
            Created {formatDateCentral(run.created_at)}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            <div className="text-center p-4 bg-muted rounded-lg">
              <div className="text-2xl font-bold">{run.total_items}</div>
              <div className="text-xs text-muted-foreground mt-1">Total Items</div>
            </div>
            {run.pending_items > 0 && (
              <div className="text-center p-4 bg-gray-50 rounded-lg">
                <div className="text-2xl font-bold text-gray-600">{run.pending_items}</div>
                <div className="text-xs text-muted-foreground mt-1">Pending</div>
              </div>
            )}
            {run.running_items > 0 && (
              <div className="text-center p-4 bg-yellow-50 rounded-lg">
                <div className="text-2xl font-bold text-yellow-600">{run.running_items}</div>
                <div className="text-xs text-muted-foreground mt-1">Running</div>
              </div>
            )}
            <div className="text-center p-4 bg-green-50 rounded-lg">
              <div className="text-2xl font-bold text-green-600">{run.succeeded_items}</div>
              <div className="text-xs text-muted-foreground mt-1">Succeeded</div>
            </div>
            {run.failed_items > 0 && (
              <div className="text-center p-4 bg-red-50 rounded-lg">
                <div className="text-2xl font-bold text-red-600">{run.failed_items}</div>
                <div className="text-xs text-muted-foreground mt-1">Failed</div>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {aiCost && aiCost.attempt_count > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>Total estimated AI usage cost</CardTitle>
            <CardDescription>
              Based on tracked model calls for this run (totals are approximate).
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="text-2xl font-semibold">
              {Number(aiCost.estimated_total).toLocaleString(undefined, {
                style: 'currency',
                currency: aiCost.currency || 'USD',
                minimumFractionDigits: 2,
                maximumFractionDigits: 6,
              })}
            </div>
            {aiCost.incomplete_estimate ? (
              <p className="text-sm text-amber-700 dark:text-amber-400">
                Some usage data was missing, so this total may be incomplete.
              </p>
            ) : null}
            {aiCost.node_breakdown?.length ? (
              <div className="text-sm text-muted-foreground">
                <div className="font-medium text-foreground mb-1">By step</div>
                <ul className="list-disc pl-5 space-y-1">
                  {aiCost.node_breakdown.map((row) => (
                    <li key={String(row.node_id)}>
                      {getNodeStepDisplayName(graph?.spec?.nodes, row.node_id)}
                      {': '}
                      {Number(row.estimated_total).toLocaleString(undefined, {
                        style: 'currency',
                        currency: aiCost.currency || 'USD',
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 6,
                      })}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </CardContent>
        </Card>
      ) : null}

      {/* Processed Items Table */}
      {run.items && run.items.length > 0 && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>Processed Items</CardTitle>
                <CardDescription>
                  Individual items processed through the flow
                </CardDescription>
              </div>
              <div className="flex items-center gap-2">
                {selectedItems.size > 0 && (
                  <>
                    <span className="text-sm text-muted-foreground">
                      {selectedItems.size} selected
                    </span>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={handleDeselectAll}
                    >
                      Clear Selection
                    </Button>
                    <Button
                      variant="default"
                      size="sm"
                      onClick={handleBulkRerun}
                      disabled={rerunningItems.size > 0}
                    >
                      {rerunningItems.size > 0 ? (
                        <>
                          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                          Rerunning...
                        </>
                      ) : (
                        <>
                          <RotateCcw className="mr-2 h-4 w-4" />
                          Rerun Selected ({selectedItems.size})
                        </>
                      )}
                    </Button>
                  </>
                )}
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleSelectFailed}
                  disabled={run.failed_items === 0}
                >
                  Select Failed ({run.failed_items})
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleSelectAll}
                >
                  Select All
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[50px]">
                    <Checkbox
                      checked={paginatedItems.length > 0 && paginatedItems.every(item => selectedItems.has(item.id))}
                      onCheckedChange={(checked) => {
                        const pageItemIds = paginatedItems.map(item => item.id)
                        if (checked) {
                          setSelectedItems(prev => new Set([...prev, ...pageItemIds]))
                        } else {
                          setSelectedItems(prev => {
                            const next = new Set(prev)
                            pageItemIds.forEach(id => next.delete(id))
                            return next
                          })
                        }
                      }}
                    />
                  </TableHead>
                  <TableHead className="w-[80px]">ID</TableHead>
                  <TableHead className="w-[250px]">Source</TableHead>
                  <TableHead className="w-[120px]">Status</TableHead>
                  <TableHead className="w-[130px] text-right">Est. cost</TableHead>
                  <TableHead className="w-[180px]">Created</TableHead>
                  <TableHead className="w-[100px]">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {paginatedItems.map((item) => (
                  <TableRow 
                    key={item.id}
                    className={`cursor-pointer hover:bg-muted/[0.07] ${selectedItems.has(item.id) ? 'bg-muted' : ''}`}
                    onClick={() => navigate(`/runs/${runId}/items/${item.id}`)}
                  >
                    <TableCell onClick={(e) => e.stopPropagation()}>
                      <Checkbox
                        checked={selectedItems.has(item.id)}
                        onCheckedChange={(checked) => handleSelectItem(item.id, checked as boolean)}
                        disabled={
                          item.status === 'pending' ||
                          item.status === 'running' ||
                          item.status === 'skipped'
                        }
                      />
                    </TableCell>
                    <TableCell className="font-mono text-xs">#{item.id}</TableCell>
                    <TableCell className="text-sm max-w-[250px]">
                      {item.source_file ? (
                        <div className="flex items-center gap-2 max-w-full">
                          <FileText className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                          <span className="font-mono text-xs truncate" title={item.source_file}>
                            {item.source_file.split('/').pop()}
                          </span>
                        </div>
                      ) : item.input_article_id ? (
                        <div className="flex flex-col gap-1 max-w-full">
                          <div className="flex items-center gap-2">
                            <FileText className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                            <span className="text-xs font-medium">DB Input</span>
                          </div>
                          {item.input_headline && (
                            <span className="text-xs text-muted-foreground truncate" title={item.input_headline}>
                              {item.input_headline.length > 40 ? `${item.input_headline.substring(0, 40)}...` : item.input_headline}
                            </span>
                          )}
                          <span className="text-xs font-mono text-muted-foreground">
                            Article ID: {item.input_article_id}
                          </span>
                        </div>
                      ) : (
                        <div className="flex flex-col gap-1 max-w-full">
                          <span className="text-xs font-medium text-muted-foreground">
                            {item.is_array_splitter_item ? 'Array input' : 'Manual input'}
                          </span>
                          {item.input_headline && (
                            <span className="text-xs text-muted-foreground truncate" title={item.input_headline}>
                              {item.input_headline.length > 40 ? `${item.input_headline.substring(0, 40)}...` : item.input_headline}
                            </span>
                          )}
                        </div>
                      )}
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-col gap-1">
                        <Badge variant="outline" className={`${getStatusColor(item.status)} w-fit`}>
                          {getStatusIcon(item.status)}
                          <span className="ml-1 capitalize">{item.status}</span>
                        </Badge>
                        {item.status === 'running' && item.current_node_types && item.current_node_types.length > 0 && (
                          <span className="text-xs text-muted-foreground">
                            Executing: {item.current_node_types.join(', ')}
                          </span>
                        )}
                      </div>
                    </TableCell>
                    <TableCell className="text-sm text-right tabular-nums">
                      <span className="inline-flex items-center justify-end gap-1">
                        {(item.estimated_ai_cost !== undefined && item.estimated_ai_cost !== null) ||
                        item.estimated_ai_cost_incomplete ? (
                          <>
                            {Number(item.estimated_ai_cost ?? 0).toLocaleString(undefined, {
                              style: 'currency',
                              currency: item.estimated_ai_cost_currency || 'USD',
                              minimumFractionDigits: 2,
                              maximumFractionDigits: 6,
                            })}
                            {item.estimated_ai_cost_incomplete ? (
                              <span
                                className="text-amber-700 dark:text-amber-400"
                                title="Some usage or pricing data was missing"
                              >
                                *
                              </span>
                            ) : null}
                          </>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </span>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {formatDateCentral(item.created_at)}
                    </TableCell>
                    <TableCell>
                      <div className="flex gap-2">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={(e) => {
                            e.stopPropagation()
                            navigate(`/runs/${runId}/items/${item.id}`)
                          }}
                        >
                          View Details
                        </Button>
                        {item.output_s3_bucket && item.output_s3_key && item.status === 'succeeded' && (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={(e) => {
                              e.stopPropagation()
                              window.open(getS3Url(item)!, '_blank')
                            }}
                            title="View on S3"
                          >
                            <ExternalLink className="h-3 w-3" />
                          </Button>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            
            {/* Pagination Controls */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between pt-4 border-t">
                <div className="text-sm text-muted-foreground">
                  Showing {startIndex + 1}-{Math.min(endIndex, totalItems)} of {totalItems} items
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                    disabled={currentPage === 1}
                  >
                    Previous
                  </Button>
                  <div className="text-sm">
                    Page {currentPage} of {totalPages}
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                    disabled={currentPage === totalPages}
                  >
                    Next
                  </Button>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* No Items Message */}
      {run.total_items === 0 && (
        <Card>
          <CardContent className="py-12">
            <div className="text-center">
              <AlertTriangle className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
              <h3 className="text-lg font-semibold mb-2">No Items Processed</h3>
              <p className="text-muted-foreground">
                This run has no processed items yet.
              </p>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
