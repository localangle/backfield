import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { Link, useParams, useNavigate, useSearchParams, useLocation } from 'react-router-dom'
import { useAppMessage } from '@/components/AppMessageProvider'
import { PageBreadcrumbs } from '@/components/PageBreadcrumbs'
import { ProcessedItemInformationCard } from '@/components/ProcessedItemInformationCard'
import { ProcessedItemVerificationSection } from '@/components/ProcessedItemVerificationSection'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { getRun, getGraph, getProcessedItem, getProject, rerunProcessedItem, type Run, type Graph, type ProcessedItem, type Project } from '@/lib/api'
import { listMyWorkspaces, type WorkspaceWithProjects } from '@/lib/core-api'
import { getVisualizationsForItem, type VisualizationDescriptor } from '@/lib/visualizations'
import { processedItemDisplayTitle } from '@/lib/review/content/displayTitle'
import {
  PROCESSED_ITEM_DETAIL_TABS,
  isProcessedItemDetailTab,
  parseProcessedItemDetailTab,
  readProcessedItemTabFromLocation,
  type ProcessedItemDetailTab,
} from '@/lib/review/content/detailTab'
import {
  RERUN_WARNING_TITLE,
  reconciliationPolicyFromGraph,
  rerunWarningBody,
} from '@/lib/rerunWarning'
import {
  Download,
  CheckCircle,
  XCircle,
  Loader2,
  AlertTriangle,
  FileText,
  ExternalLink,
  RotateCcw,
} from 'lucide-react'
import JsonView from '@uiw/react-json-view'

type JsonOutputView = 'reviewed' | 'original'

const PROCESSED_ITEM_TAB_LABELS: Record<ProcessedItemDetailTab, string> = {
  info: 'Info',
  places: 'Places',
  people: 'People',
  organizations: 'Organizations',
  events: 'Events',
  works: 'Works',
  images: 'Images',
  meta: 'Meta',
  json: 'JSON',
}

export default function ProcessedItemDetail() {
  const { showError, showConfirm } = useAppMessage()
  const { runId, itemId } = useParams<{ runId: string; itemId: string }>()
  const navigate = useNavigate()
  const location = useLocation()
  const [searchParams, setSearchParams] = useSearchParams()
  const verificationDirtyRef = useRef(false)
  /** Set once a rerun reaches pending/running; gates clearing ``rerunRequested``. */
  const rerunSawInFlightRef = useRef(false)
  const [reviewDirty, setReviewDirty] = useState(false)
  const [run, setRun] = useState<Run | null>(null)
  const [graph, setGraph] = useState<Graph | null>(null)
  const [item, setItem] = useState<ProcessedItem | null>(null)
  const [loading, setLoading] = useState(true)
  const [rerunning, setRerunning] = useState(false)
  /** True after the user confirms rerun until the item leaves pending/running. */
  const [rerunRequested, setRerunRequested] = useState(false)
  const [visualizations, setVisualizations] = useState<VisualizationDescriptor[]>([])
  const [catalogProject, setCatalogProject] = useState<Project | null>(null)
  const [projectWorkspace, setProjectWorkspace] = useState<WorkspaceWithProjects | null>(null)
  const [jsonOutputView, setJsonOutputView] = useState<JsonOutputView>('reviewed')

  const hasReviewedOutput = Boolean(
    item?.reviewed_output &&
      typeof item.reviewed_output === 'object' &&
      Object.keys(item.reviewed_output).length > 0,
  )

  useEffect(() => {
    if (hasReviewedOutput) {
      setJsonOutputView('reviewed')
    } else {
      setJsonOutputView('original')
    }
  }, [item?.id, item?.overlay_version, hasReviewedOutput])

  const handleVerificationDirtyChange = useCallback((dirty: boolean) => {
    verificationDirtyRef.current = dirty
    setReviewDirty(dirty)
  }, [])

  const itemSynthetic = item?.synthetic ?? false
  const activeTab = useMemo(
    () =>
      parseProcessedItemDetailTab(readProcessedItemTabFromLocation(searchParams), {
        synthetic: itemSynthetic,
      }),
    [searchParams, itemSynthetic],
  )

  // Promote ``#tab`` links to ``?tab=`` so the URL stays shareable with one source of truth.
  useEffect(() => {
    const fromQuery = searchParams.get('tab')?.trim()
    if (fromQuery) return
    const hash = location.hash.replace(/^#/, '').trim()
    if (!hash) return
    const tab = parseProcessedItemDetailTab(hash, { synthetic: itemSynthetic })
    navigate({ pathname: location.pathname, search: `?tab=${encodeURIComponent(tab)}` }, { replace: true })
  }, [location.pathname, location.hash, searchParams, itemSynthetic, navigate])

  const handleTabChange = useCallback(
    async (next: string) => {
      if (!isProcessedItemDetailTab(next) || next === activeTab) return
      if (verificationDirtyRef.current) {
        const leave = await showConfirm(
          'Save your changes before leaving, or stay on this page to keep editing.',
          {
            title: 'Unsaved changes',
            confirmLabel: 'Leave without saving',
            cancelLabel: 'Stay',
            destructive: true,
          },
        )
        if (!leave) return
      }
      setSearchParams({ tab: next }, { replace: true })
    },
    [activeTab, setSearchParams, showConfirm],
  )

  useEffect(() => {
    if (runId && itemId) {
      loadItemData()
    }
  }, [runId, itemId])

  useEffect(() => {
    if (!run?.project_id) {
      setCatalogProject(null)
      return
    }
    let cancelled = false
    void getProject(run.project_id)
      .then((p) => {
        if (!cancelled) setCatalogProject(p)
      })
      .catch(() => {
        if (!cancelled) setCatalogProject(null)
      })
    return () => {
      cancelled = true
    }
  }, [run?.project_id])

  useEffect(() => {
    if (catalogProject?.workspace_id == null) {
      setProjectWorkspace(null)
      return
    }
    let cancelled = false
    ;(async () => {
      try {
        const rows = await listMyWorkspaces()
        if (cancelled) return
        setProjectWorkspace(rows.find((row) => row.id === catalogProject.workspace_id) ?? null)
      } catch {
        if (!cancelled) setProjectWorkspace(null)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [catalogProject?.workspace_id])

  const breadcrumbItems = useMemo(() => {
    const items: { label: string; to?: string }[] = [{ label: 'Workspaces', to: '/' }]
    if (projectWorkspace) {
      items.push({
        label: projectWorkspace.name,
        to: `/workspace/${encodeURIComponent(projectWorkspace.slug)}`,
      })
    }
    if (catalogProject) {
      items.push({
        label: catalogProject.name,
        to: `/project/${encodeURIComponent(catalogProject.slug)}`,
      })
    }
    if (runId) {
      items.push({
        label: 'Run',
        to: `/runs/${runId}`,
      })
    }
    return items
  }, [projectWorkspace, catalogProject, runId])

  // Auto-refresh for pending or running items (but only update if data changed)
  useEffect(() => {
    if (item && !item.synthetic && (item.status === 'pending' || item.status === 'running')) {
      // Add random jitter to prevent thundering herd
      const baseInterval = 5000 // 5 seconds base interval
      const jitter = Math.random() * 1000 // Random 0-1 second jitter
      const pollInterval = baseInterval + jitter
      
      const interval = setInterval(async () => {
        if (!runId || !itemId) return
        
        try {
          const [runData, itemData] = await Promise.all([
            getRun(runId),
            getProcessedItem(runId, parseInt(itemId, 10)),
          ])
          
          // Only update state if data has actually changed
          if (JSON.stringify(runData) !== JSON.stringify(run)) {
            setRun(runData)
          }
          if (JSON.stringify(itemData) !== JSON.stringify(item)) {
            setItem(itemData)
          }
        } catch (error) {
          console.error('Failed to refresh item:', error)
        }
      }, pollInterval)
      return () => clearInterval(interval)
    }
    return () => {}
  }, [item, run, runId, itemId])

  useEffect(() => {
    if (!rerunRequested || !item) return
    if (item.status === 'pending' || item.status === 'running') {
      rerunSawInFlightRef.current = true
      return
    }
    const finished =
      item.status === 'succeeded' ||
      item.status === 'failed' ||
      item.status === 'timed_out' ||
      item.status === 'skipped'
    if (finished && rerunSawInFlightRef.current) {
      setRerunRequested(false)
      rerunSawInFlightRef.current = false
    }
  }, [item?.status, item?.id, rerunRequested, item])

  const rerunBusy = rerunning || rerunRequested

  async function loadItemData() {
    if (!runId || !itemId) return

    const parsedItemId = parseInt(itemId, 10)
    if (Number.isNaN(parsedItemId)) {
      setItem(null)
      setLoading(false)
      return
    }

    try {
      setLoading(true)
      const runData = await getRun(runId)
      const graphData = await getGraph(runData.graph_id)
      setRun(runData)
      setGraph(graphData)

      try {
        const itemData = await getProcessedItem(runId, parsedItemId)
        setItem(itemData)
      } catch {
        const syn = runData.items?.find((i) => i.id === parsedItemId && i.synthetic)
        if (syn) {
          const outs = runData.node_outputs ?? {}
          setItem({
            id: syn.id,
            run_id: runId,
            synthetic: true,
            source_file: null,
            input: {},
            output: Object.keys(outs).length ? outs : null,
            node_outputs: outs,
            node_logs: null,
            status:
              syn.status === 'succeeded'
                ? 'succeeded'
                : syn.status === 'failed'
                  ? 'failed'
                  : syn.status === 'timed_out'
                    ? 'timed_out'
                    : 'failed',
            error: syn.error,
            created_at: syn.created_at,
            updated_at: syn.updated_at,
            estimated_ai_cost: syn.estimated_ai_cost,
            estimated_ai_cost_incomplete: syn.estimated_ai_cost_incomplete,
            estimated_ai_cost_currency: syn.estimated_ai_cost_currency,
          })
        } else {
          setItem(null)
        }
      }
    } catch (error) {
      console.error('Failed to load item data:', error)
      setItem(null)
    } finally {
      setLoading(false)
    }
  }

  const jsonDisplayOutput = useMemo(() => {
    if (!item?.output) return null
    if (jsonOutputView === 'reviewed' && item.reviewed_output) {
      return item.reviewed_output
    }
    return item.output
  }, [item?.output, item?.reviewed_output, jsonOutputView])

  const downloadJsonOutput = useCallback(
    (view: JsonOutputView) => {
      const payload =
        view === 'reviewed' && item?.reviewed_output ? item.reviewed_output : item?.output
      if (!payload) return

      const dataStr = JSON.stringify(payload, null, 2)
      const dataBlob = new Blob([dataStr], { type: 'application/json' })
      const url = URL.createObjectURL(dataBlob)
      const link = document.createElement('a')
      link.href = url
      link.download =
        view === 'reviewed'
          ? `run-${runId}-item-${itemId}-reviewed-output.json`
          : `run-${runId}-item-${itemId}-output.json`
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      URL.revokeObjectURL(url)
    },
    [item?.output, item?.reviewed_output, runId, itemId],
  )

  const formatJson = (data: any) => {
    try {
      return JSON.stringify(data, null, 2)
    } catch {
      return String(data)
    }
  }

  // Sanitize data for JSON viewer by removing/truncating large geometry objects
  const sanitizeForJsonView = (data: any, depth = 0): any => {
    if (depth > 20) return '[Max depth reached]' // Prevent infinite recursion
    
    if (data === null || data === undefined) {
      return data
    }
    
    if (typeof data !== 'object') {
      return data
    }
    
    if (Array.isArray(data)) {
      // For boundaries/geometry arrays, check if they're large GeoJSON geometries
      if (depth > 0 && data.length > 0) {
        const firstItem = data[0]
        // Check if this looks like a GeoJSON geometry array
        if (firstItem && typeof firstItem === 'object' && ('type' in firstItem || Array.isArray(firstItem))) {
          // Estimate size by checking nested array depth and length
          const estimateSize = (arr: any[], maxDepth = 3): number => {
            if (maxDepth === 0) return arr.length
            return arr.reduce((sum, item) => {
              if (Array.isArray(item)) {
                return sum + estimateSize(item, maxDepth - 1)
              }
              return sum + 1
            }, 0)
          }
          
          const estimatedSize = estimateSize(data)
          if (estimatedSize > 100) {
            const geomType = (firstItem as any)?.type || 'geometry'
            return {
              _truncated: true,
              type: geomType,
              count: data.length,
              note: `Large geometry array with ~${estimatedSize} coordinate points - truncated for display`,
              preview: Array.isArray(firstItem) ? `[coordinates: ${firstItem.length} points...]` : `[${geomType} geometry...]`
            }
          }
        }
      }
      
      // Check if this is a large coordinate array
      if (depth > 2 && data.length > 100) {
        return `[Array with ${data.length} items - truncated for display]`
      }
      
      return data.map((item, idx) => {
        // Truncate very large arrays
        if (idx >= 50 && data.length > 50) {
          return `[... ${data.length - 50} more items]`
        }
        return sanitizeForJsonView(item, depth + 1)
      }).slice(0, 50)
    }
    
    // Handle objects
    const sanitized: any = {}
    for (const [key, value] of Object.entries(data)) {
      if (key === '__outputKeysByNodeId' || key.startsWith('__')) {
        continue
      }
      // Remove or truncate large geometry fields
      if (key === 'boundaries' || key === 'geometry') {
        if (Array.isArray(value) && value.length > 0) {
          const firstItem = value[0]
          if (firstItem && typeof firstItem === 'object') {
            // Check if it's a GeoJSON geometry object
            if ('type' in firstItem && ('coordinates' in firstItem || 'geometries' in firstItem)) {
              sanitized[key] = {
                _truncated: true,
                type: firstItem.type || 'unknown',
                count: value.length,
                note: `Large geometry array (${value.length} feature${value.length !== 1 ? 's' : ''}) - truncated for display`,
                bbox: firstItem.bbox || null
              }
            } else {
              // Might be nested coordinate arrays
              sanitized[key] = {
                _truncated: true,
                count: value.length,
                note: `Large coordinate array - truncated for display`
              }
            }
          } else {
            sanitized[key] = `[Array with ${value.length} items - geometry data truncated]`
          }
        } else if (value && typeof value === 'object' && 'type' in value) {
          // Single geometry object - check if it has large coordinates
          const hasLargeCoords = 'coordinates' in value && 
            Array.isArray(value.coordinates) && 
            JSON.stringify(value.coordinates).length > 5000
          
          if (hasLargeCoords) {
            sanitized[key] = {
              _truncated: true,
              type: value.type || 'unknown',
              note: `Large geometry with extensive coordinate data - truncated for display`,
              bbox: value.bbox || null
            }
          } else {
            sanitized[key] = value
          }
        } else {
          sanitized[key] = value
        }
      } else {
        sanitized[key] = sanitizeForJsonView(value, depth + 1)
      }
    }
    
    return sanitized
  }

  const getS3Url = (item: ProcessedItem): string | null => {
    if (!item.output) return null
    
    const s3Bucket = item.output.s3_bucket
    const s3Key = item.output.s3_key
    
    if (s3Bucket && s3Key) {
      return `https://${s3Bucket}.s3.amazonaws.com/${s3Key}`
    }
    
    return null
  }

  // Load visualizations asynchronously
  useEffect(() => {
    if (!item || !graph) {
      setVisualizations([])
      return
    }
    
    getVisualizationsForItem({ item, graph }).then(setVisualizations).catch((error) => {
      console.error('Failed to load visualizations:', error)
      setVisualizations([])
    })
  }, [item, graph])

  const mapboxToken = run?.mapbox_api_token ?? (import.meta.env.VITE_MAPBOX_API_TOKEN as string | undefined) ?? null

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (!item) {
    return (
      <div className="space-y-6">
        <PageBreadcrumbs items={[...breadcrumbItems, { label: 'Item' }]} />
        <div className="flex items-center justify-center py-12">
          <div className="text-center">
            <AlertTriangle className="mx-auto mb-4 h-12 w-12 text-muted-foreground" />
            <h2 className="mb-2 text-xl font-semibold">Processed Item Not Found</h2>
            <p className="text-muted-foreground">
              The processed item you're looking for doesn't exist or has been deleted.
            </p>
          </div>
        </div>
      </div>
    )
  }

  const pageTitle = processedItemDisplayTitle(item)

  return (
    <div className="space-y-6">
      {item.synthetic && (
        <Alert>
          <AlertDescription>
            This run completed as a single graph execution (for example Text Input or JSON Input). There is
            no separate batch item in the database; the node outputs below are the full run result.
          </AlertDescription>
        </Alert>
      )}
      {/* Header */}
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0 space-y-3">
          <PageBreadcrumbs items={[...breadcrumbItems, { label: 'Item' }]} />
          <div className="min-w-0">
            <h1 className="text-2xl font-bold leading-tight sm:text-3xl">{pageTitle}</h1>
            {run?.graph_id ? (
              <p className="mt-1 text-sm text-muted-foreground">
                Flow:{' '}
                <Link
                  to={`/flow/${encodeURIComponent(run.graph_id)}`}
                  className="font-medium text-primary hover:underline"
                >
                  {graph?.name || `Flow ${run.graph_id}`}
                </Link>
              </p>
            ) : null}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {item.status === 'succeeded' && item.output && getS3Url(item) && (
            <Button
              variant="outline"
              onClick={() => window.open(getS3Url(item)!, '_blank')}
            >
              <ExternalLink className="mr-2 h-4 w-4" />
              View on S3
            </Button>
          )}
          {!item.synthetic && (
            <Button
              variant="default"
              disabled={
                rerunBusy || item.status === 'pending' || item.status === 'running'
              }
              onClick={async () => {
                if (!runId || !itemId) return
                const policy = reconciliationPolicyFromGraph(graph)
                const ok = await showConfirm(rerunWarningBody(1, { flowName: graph?.name, policy }), {
                  title: RERUN_WARNING_TITLE,
                  confirmLabel: 'Rerun',
                  destructive: policy === 'replace',
                })
                if (!ok) return
                rerunSawInFlightRef.current = false
                setRerunRequested(true)
                try {
                  setRerunning(true)
                  const rerunRes = await rerunProcessedItem(runId, parseInt(itemId, 10))
                  if (rerunRes.status === 'pending' || rerunRes.status === 'running') {
                    rerunSawInFlightRef.current = true
                    setItem((prev) =>
                      prev
                        ? {
                            ...prev,
                            status: rerunRes.status as ProcessedItem['status'],
                            output: null,
                            reviewed_output: null,
                            overlay: null,
                            error: null,
                          }
                        : prev,
                    )
                  }
                  await loadItemData()
                } catch (e) {
                  setRerunRequested(false)
                  rerunSawInFlightRef.current = false
                  console.error('Failed to rerun item:', e)
                  const detail =
                    e instanceof Error && e.message.startsWith('API error:')
                      ? e.message.replace(/^API error: \d+ - /, '').trim()
                      : null
                  showError(
                    detail && detail.length < 200
                      ? detail
                      : 'Failed to rerun item. Please try again.',
                  )
                } finally {
                  setRerunning(false)
                }
              }}
            >
              {rerunBusy ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <RotateCcw className="mr-2 h-4 w-4" />
              )}
              {rerunBusy ? 'Rerunning...' : 'Rerun Item'}
            </Button>
          )}
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={(v) => void handleTabChange(v)} className="space-y-4">
        <TabsList className="w-full h-auto flex flex-wrap justify-start gap-1 p-1">
          {PROCESSED_ITEM_DETAIL_TABS.map((tab) => (
            <TabsTrigger key={tab} value={tab}>
              {PROCESSED_ITEM_TAB_LABELS[tab]}
            </TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value="info" className="space-y-4">
          <ProcessedItemInformationCard
            runId={runId!}
            item={item}
            onItemUpdated={(next) => setItem({ ...next, synthetic: item.synthetic })}
            reviewDirty={reviewDirty}
          />

      {/* Error Display */}
      {item.error && (
        <Card className="border-destructive">
          <CardHeader>
            <CardTitle className="text-destructive flex items-center gap-2">
              <XCircle className="h-5 w-5" />
              Error
            </CardTitle>
          </CardHeader>
          <CardContent>
            <pre className="text-sm text-destructive whitespace-pre-wrap font-mono bg-destructive/10 p-4 rounded">
              {item.error}
            </pre>
          </CardContent>
        </Card>
      )}

          {/* Image Embeddings */}
          {(() => {
            if (!item.output) return null
            
            const output = item.output as any
            
            // Find image embedding arrays in the output
            // Look for arrays that contain objects with generated_text and embedding_model
            const findImageEmbeddings = (obj: any, path: string = ''): Array<{ data: any[], fieldName: string }> => {
              const results: Array<{ data: any[], fieldName: string }> = []
              
              if (Array.isArray(obj)) {
                // Check if this array contains image embedding objects
                const hasImageEmbeddings = obj.length > 0 && 
                  obj.every((item: any) => 
                    item && 
                    typeof item === 'object' && 
                    'generated_text' in item && 
                    'embedding_model' in item &&
                    ('url' in item || 'base64' in item)
                  )
                
                if (hasImageEmbeddings) {
                  results.push({ data: obj, fieldName: path || 'results' })
                }
              } else if (obj && typeof obj === 'object') {
                // Recursively search through object properties
                for (const [key, value] of Object.entries(obj)) {
                  if (Array.isArray(value)) {
                    const hasImageEmbeddings = value.length > 0 && 
                      value.every((item: any) => 
                        item && 
                        typeof item === 'object' && 
                        'generated_text' in item && 
                        'embedding_model' in item &&
                        ('url' in item || 'base64' in item)
                      )
                    
                    if (hasImageEmbeddings) {
                      results.push({ data: value, fieldName: key })
                    }
                  } else if (value && typeof value === 'object') {
                    results.push(...findImageEmbeddings(value, key))
                  }
                }
              }
              
              return results
            }
            
            const imageEmbeddingArrays = findImageEmbeddings(output)
            
            if (imageEmbeddingArrays.length === 0) return null
            
            // Flatten all image embeddings from all arrays
            const allImageEmbeddings = imageEmbeddingArrays.flatMap(({ data }) => data)
            
            if (allImageEmbeddings.length === 0) return null
            
            return (
              <Card>
                <CardHeader>
                  <CardTitle>Image Embeddings ({allImageEmbeddings.length})</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {allImageEmbeddings.map((embedding: any, idx: number) => {
                      const imgUrl = embedding.url || embedding.base64
                      const generatedText = embedding.generated_text
                      const embeddingModel = embedding.embedding_model || 'text-embedding-3-small'
                      const embeddingDimensions = embedding.embedding_dimensions || embedding.embedding?.length || 0
                      
                      return (
                        <Card key={idx} className="overflow-hidden">
                          <CardContent className="p-0">
                            <div className="flex flex-col md:flex-row">
                              {imgUrl && (
                                <div className="relative w-full md:w-1/2 aspect-video md:aspect-square bg-muted flex-shrink-0">
                                  <img
                                    src={imgUrl}
                                    alt={embedding.caption || `Image ${idx + 1}`}
                                    className="w-full h-full object-cover"
                                    onError={(e) => {
                                      (e.target as HTMLImageElement).style.display = 'none'
                                    }}
                                  />
                                </div>
                              )}
                              <div className="p-4 space-y-2 flex-1">
                                {generatedText && (
                                  <div>
                                    <label className="text-xs font-medium text-muted-foreground">Generated Description</label>
                                    <p className="text-sm mt-1 whitespace-pre-wrap break-words">
                                      {String(generatedText)}
                                    </p>
                                  </div>
                                )}
                                <div className="flex items-center gap-2 text-xs text-muted-foreground pt-2 border-t">
                                  <span className="font-medium">Model:</span>
                                  <span>{embeddingModel}</span>
                                  {embeddingDimensions > 0 && (
                                    <>
                                      <span className="mx-1">•</span>
                                      <span>{embeddingDimensions} dimensions</span>
                                    </>
                                  )}
                                </div>
                              </div>
                            </div>
                          </CardContent>
                        </Card>
                      )
                    })}
                  </div>
                </CardContent>
              </Card>
            )
          })()}

          {visualizations.length > 0 && visualizations.map((viz: VisualizationDescriptor, vizIndex: number) => {
              const VisualizationComponent = viz.component
              // Use node-specific output if available, otherwise fall back to item.output
              const output = viz.nodeOutput ?? item?.output ?? {}
              const vizKey = viz.id || `${viz.nodeId}-${vizIndex}`
              return (
                <VisualizationComponent
                  key={vizKey}
                  nodeId={viz.nodeId}
                  nodeLabel={viz.description || viz.title}
                  output={output}
                  mapboxToken={mapboxToken || undefined}
                  data={viz.data}
                />
              )
            })}
        </TabsContent>

        <TabsContent value="places" className="space-y-4">
          {!item.synthetic ? (
            <ProcessedItemVerificationSection
              runId={runId!}
              item={item}
              graph={graph}
              onItemUpdated={(next) => setItem({ ...next, synthetic: false })}
              onVerificationDirtyChange={handleVerificationDirtyChange}
              catalogStylebookSlug={catalogProject?.workspace_stylebook_slug ?? null}
              catalogProjectSlug={catalogProject?.slug ?? null}
            />
          ) : (
            <Card>
              <CardContent className="py-10 text-center text-sm text-muted-foreground">
                Place review is available for batch stories. This run used a single input and has no
                separate story item.
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {(
          [
            ['people', 'People'],
            ['organizations', 'Organizations'],
            ['events', 'Events'],
            ['works', 'Works'],
            ['images', 'Images'],
            ['meta', 'Meta'],
          ] as const
        ).map(([value, label]) => (
          <TabsContent key={value} value={value} className="space-y-4">
            <Card>
              <CardContent className="py-10 text-center text-sm text-muted-foreground">
                {label} review is not available yet.
              </CardContent>
            </Card>
          </TabsContent>
        ))}

        <TabsContent value="json" className="space-y-4">
          {item.output && Object.keys(item.output).length > 0 ? (
            <Card>
              <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div className="space-y-1">
                  <CardTitle>Output Data</CardTitle>
                  {hasReviewedOutput ? (
                    <p className="text-sm text-muted-foreground">
                      Reviewed output includes changes made through the review interface.
                    </p>
                  ) : null}
                </div>
                {item.status === 'succeeded' && item.output ? (
                  <div className="flex flex-wrap items-center gap-2">
                    {hasReviewedOutput ? (
                      <div className="flex rounded-md border p-0.5" role="group" aria-label="Output data version">
                        <Button
                          type="button"
                          variant={jsonOutputView === 'reviewed' ? 'default' : 'ghost'}
                          size="sm"
                          className="h-8"
                          onClick={() => setJsonOutputView('reviewed')}
                        >
                          Reviewed
                        </Button>
                        <Button
                          type="button"
                          variant={jsonOutputView === 'original' ? 'default' : 'ghost'}
                          size="sm"
                          className="h-8"
                          onClick={() => setJsonOutputView('original')}
                        >
                          Original
                        </Button>
                      </div>
                    ) : null}
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => downloadJsonOutput(jsonOutputView)}
                    >
                      <Download className="mr-2 h-4 w-4" />
                      Download
                    </Button>
                  </div>
                ) : null}
              </CardHeader>
              <CardContent>
                <div className="rounded border overflow-auto max-h-[600px] [&_*]:break-words">
                  <JsonView
                    value={sanitizeForJsonView(jsonDisplayOutput ?? item.output)}
                    style={{
                      backgroundColor: 'transparent',
                      fontSize: '0.875rem',
                    }}
                    collapsed={false}
                    displayDataTypes={false}
                    displayObjectSize={false}
                  />
                </div>
              </CardContent>
            </Card>
          ) : (
            <Card>
              <CardContent className="py-12">
                <div className="text-center">
                  {item.status === 'running' || item.status === 'pending' ? (
                    <>
                      <Loader2 className="h-12 w-12 text-muted-foreground mx-auto mb-4 animate-spin" />
                      <h3 className="text-lg font-semibold mb-2">Awaiting Output</h3>
                      <p className="text-muted-foreground">
                        Output will appear here once processing finishes.
                      </p>
                    </>
                  ) : (
                    <>
                      <CheckCircle className="h-12 w-12 text-green-500 mx-auto mb-4" />
                      <h3 className="text-lg font-semibold mb-2">No Output Generated</h3>
                      <p className="text-muted-foreground">
                        This item completed without producing final JSON output.
                      </p>
                    </>
                  )}
                </div>
              </CardContent>
            </Card>
          )}
        </TabsContent>
      </Tabs>
    </div>
  )
}

