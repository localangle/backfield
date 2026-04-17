import { useState, useEffect, useMemo } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { getNodeOutputById } from '@/lib/nodeOutputs'
import { getRun, getGraph, getProcessedItem, rerunProcessedItem, type Run, type Graph, type ProcessedItem } from '@/lib/api'
import { getVisualizationsForItem, type VisualizationDescriptor } from '@/lib/visualizations'
import { formatDateCentral } from '@/lib/utils'
import { ArrowLeft, Download, CheckCircle, XCircle, Clock, Loader2, AlertTriangle, FileText, ExternalLink } from 'lucide-react'
import JsonView from '@uiw/react-json-view'

export default function ProcessedItemDetail() {
  const { runId, itemId } = useParams<{ runId: string; itemId: string }>()
  const navigate = useNavigate()
  const [run, setRun] = useState<Run | null>(null)
  const [graph, setGraph] = useState<Graph | null>(null)
  const [item, setItem] = useState<ProcessedItem | null>(null)
  const [loading, setLoading] = useState(true)
  const [rerunning, setRerunning] = useState(false)
  const [visualizations, setVisualizations] = useState<VisualizationDescriptor[]>([])

  useEffect(() => {
    if (runId && itemId) {
      loadItemData()
    }
  }, [runId, itemId])

  // Auto-refresh for pending or running items (but only update if data changed)
  useEffect(() => {
    if (item && (item.status === 'pending' || item.status === 'running')) {
      // Add random jitter to prevent thundering herd
      const baseInterval = 5000 // 5 seconds base interval
      const jitter = Math.random() * 1000 // Random 0-1 second jitter
      const pollInterval = baseInterval + jitter
      
      const interval = setInterval(async () => {
        if (!runId || !itemId) return
        
        try {
          const [runData, itemData] = await Promise.all([
            getRun(runId),
            getProcessedItem(runId, parseInt(itemId))
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

  async function loadItemData() {
    if (!runId || !itemId) return

    try {
      setLoading(true)
      // Load run summary and full item details in parallel
      const [runData, itemData, graphData] = await Promise.all([
        getRun(runId),
        getProcessedItem(runId, parseInt(itemId)),
        getRun(runId).then(r => getGraph(r.graph_id))
      ])
      setRun(runData)
      setItem(itemData)
      setGraph(graphData)
    } catch (error) {
      console.error('Failed to load item data:', error)
    } finally {
      setLoading(false)
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
      default:
        return <Clock className="h-4 w-4" />
    }
  }

  const handleDownloadOutput = () => {
    if (!item?.output) return

    const dataStr = JSON.stringify(item.output, null, 2)
    const dataBlob = new Blob([dataStr], { type: 'application/json' })
    const url = URL.createObjectURL(dataBlob)
    const link = document.createElement('a')
    link.href = url
    link.download = `run-${runId}-item-${itemId}-output.json`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
  }

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
      <div className="flex items-center justify-center py-12">
        <div className="text-center">
          <AlertTriangle className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
          <h2 className="text-xl font-semibold mb-2">Processed Item Not Found</h2>
          <p className="text-muted-foreground mb-4">
            The processed item you're looking for doesn't exist or has been deleted.
          </p>
          <Button onClick={() => navigate(`/runs/${runId}`)}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back to Run
          </Button>
        </div>
      </div>
    )
  }

  const nodeOutputs = item.node_outputs ?? {}
  const nodeLogs = item.node_logs ?? {}
  const rawOutputs = nodeOutputs as Record<string, unknown>
  const hasNodeOutput = (nodeId: string) => getNodeOutputById(rawOutputs, nodeId) !== undefined
  const uniqueNodeIds = new Set<string>([...Object.keys(nodeLogs)])
  if (graph?.spec?.nodes) {
    for (const node of graph.spec.nodes) {
      if (hasNodeOutput(node.id)) {
        uniqueNodeIds.add(node.id)
      }
    }
  } else {
    for (const k of Object.keys(nodeOutputs)) {
      if (k !== '__outputKeysByNodeId') uniqueNodeIds.add(k)
    }
  }
  const orderedNodeIds: string[] = []
  if (graph?.spec?.nodes) {
    for (const node of graph.spec.nodes) {
      if (uniqueNodeIds.has(node.id)) {
        orderedNodeIds.push(node.id)
        uniqueNodeIds.delete(node.id)
      }
    }
  }
  uniqueNodeIds.forEach((id) => orderedNodeIds.push(id))

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button variant="ghost" onClick={() => navigate(`/runs/${runId}`)}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back to Run
          </Button>
          <div>
            <h1 className="text-3xl font-bold">Processed Item #{item.id}</h1>
            <p className="text-muted-foreground mt-1">
              {graph?.name || `Flow ${run?.graph_id}`} • Run #{runId}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {item.status === 'succeeded' && item.output && getS3Url(item) && (
            <Button
              variant="outline"
              onClick={() => window.open(getS3Url(item)!, '_blank')}
            >
              <ExternalLink className="mr-2 h-4 w-4" />
              View on S3
            </Button>
          )}
          {item.status === 'succeeded' && item.output && (
            <Button onClick={handleDownloadOutput}>
              <Download className="mr-2 h-4 w-4" />
              Download Output
            </Button>
          )}
          <Button
            variant="default"
            disabled={rerunning || item.status === 'pending' || item.status === 'running'}
            onClick={async () => {
              if (!runId || !itemId) return
              try {
                setRerunning(true)
                await rerunProcessedItem(runId, parseInt(itemId))
                // Reload the item data to show updated status
                await loadItemData()
              } catch (e) {
                console.error('Failed to rerun item:', e)
                alert('Failed to rerun item. Please try again.')
              } finally {
                setRerunning(false)
              }
            }}
          >
            {rerunning ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <FileText className="mr-2 h-4 w-4" />
            )}
            Rerun Item
          </Button>
        </div>
      </div>

      {/* Item Metadata */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            Item Information
            <Badge className={getStatusColor(item.status)}>
              {getStatusIcon(item.status)}
              <span className="ml-1 capitalize">{item.status}</span>
            </Badge>
          </CardTitle>
          {item.source_file && (
            <CardDescription className="font-mono text-xs">
              <FileText className="inline h-3 w-3 mr-1" />
              {item.source_file}
            </CardDescription>
          )}
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-sm font-medium text-muted-foreground">Item ID</label>
              <p className="text-lg font-mono">#{item.id}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-muted-foreground">Run ID</label>
              <p className="text-lg font-mono">#{item.run_id}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-muted-foreground">Created</label>
              <p className="text-sm">
                {formatDateCentral(item.created_at)}
              </p>
            </div>
            {item.status !== 'pending' && (
              <div>
                <label className="text-sm font-medium text-muted-foreground">Completed</label>
                <p className="text-sm">
                  {formatDateCentral(item.updated_at)}
                </p>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

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

      <Tabs defaultValue="visuals" className="space-y-4">
        <TabsList className="w-full sm:w-auto">
          <TabsTrigger value="visuals">Visuals</TabsTrigger>
          <TabsTrigger value="json">JSON</TabsTrigger>
          <TabsTrigger value="debug">Debug</TabsTrigger>
        </TabsList>

        <TabsContent value="visuals" className="space-y-4">
          {/* Top-line Text Attributes */}
          {(() => {
            if (!item.output) return null
            
            const output = item.output as any
            const textAttributes = [
              { key: 'publication', label: 'Publication' },
              { key: 'headline', label: 'Headline' },
              { key: 'url', label: 'URL', isLink: true },
              { key: 'author', label: 'Author' },
              { key: 'pub_date', label: 'Publication Date' },
              { key: 'updated', label: 'Updated' },
            ]
            
            const hasTextAttributes = textAttributes.some(attr => output[attr.key])
            
            if (!hasTextAttributes) return null
            
            return (
              <Card>
                <CardHeader>
                  <CardTitle>Article Information</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {textAttributes.map(({ key, label, isLink }) => {
                      const value = output[key]
                      if (!value) return null
                      
                      return (
                        <div key={key} className="space-y-1">
                          <label className="text-sm font-medium text-muted-foreground">{label}</label>
                          {isLink ? (
                            <div>
                              <a
                                href={value}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-sm text-blue-600 hover:text-blue-800 hover:underline flex items-center gap-1"
                              >
                                {value}
                                <ExternalLink className="h-3 w-3" />
                              </a>
                            </div>
                          ) : (
                            <p className="text-sm break-words">{String(value)}</p>
                          )}
                        </div>
                      )
                    })}
                  </div>
                  
                  {output.text && (
                    <div className="space-y-1 pt-2 border-t">
                      <label className="text-sm font-medium text-muted-foreground">Text</label>
                      <p className="text-sm text-muted-foreground whitespace-pre-wrap break-words max-h-48 overflow-y-auto">
                        {String(output.text)}
                      </p>
                    </div>
                  )}
                  
                  {output.images && Array.isArray(output.images) && output.images.length > 0 && (
                    <div className="space-y-1 pt-2 border-t">
                      <label className="text-sm font-medium text-muted-foreground">Images ({output.images.length})</label>
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mt-2">
                        {output.images.slice(0, 8).map((img: any, idx: number) => {
                          const imgUrl = img.url || img.base64
                          if (!imgUrl) return null
                          
                          return (
                            <div key={idx} className="relative aspect-video bg-muted rounded overflow-hidden">
                              <img
                                src={imgUrl}
                                alt={img.caption || `Image ${idx + 1}`}
                                className="w-full h-full object-cover"
                                onError={(e) => {
                                  (e.target as HTMLImageElement).style.display = 'none'
                                }}
                              />
                            </div>
                          )
                        })}
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
            )
          })()}

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

          {/* Check if we have any content to show */}
          {(() => {
            if (!item.output) {
              if (visualizations.length === 0) {
                return (
                  <Card>
                    <CardContent className="py-10 text-center text-sm text-muted-foreground">
                      No visualizations are available for this processed item yet.
                    </CardContent>
                  </Card>
                )
              }
              return null
            }
            
            const output = item.output as any
            
            // Check for article information
            const textAttributes = ['publication', 'headline', 'url', 'author', 'pub_date', 'updated']
            const hasArticleInfo = textAttributes.some(attr => output[attr]) || output.text || (Array.isArray(output.images) && output.images.length > 0)
            
            // Check for image embeddings
            const findImageEmbeddings = (obj: any): boolean => {
              if (Array.isArray(obj)) {
                return obj.length > 0 && obj.some((item: any) => 
                  item && typeof item === 'object' && 'generated_text' in item && 'embedding_model' in item
                )
              }
              if (obj && typeof obj === 'object') {
                return Object.values(obj).some(value => findImageEmbeddings(value))
              }
              return false
            }
            const hasImageEmbeddings = findImageEmbeddings(output)

            // Only show "No visualizations" if we have no visualizations AND no article info AND no image embeddings
            if (visualizations.length === 0 && !hasArticleInfo && !hasImageEmbeddings) {
              return (
            <Card>
              <CardContent className="py-10 text-center text-sm text-muted-foreground">
                No visualizations are available for this processed item yet.
              </CardContent>
            </Card>
              )
            }
            
            return null
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

        <TabsContent value="json" className="space-y-4">
          {item.output && Object.keys(item.output).length > 0 ? (
            <Card>
              <CardHeader>
                <CardTitle>Output Data</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="rounded border overflow-auto max-h-[600px] [&_*]:break-words">
                  <JsonView
                    value={sanitizeForJsonView(item.output)}
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

        <TabsContent value="debug" className="space-y-4">
          {item.input && Object.keys(item.input).length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Input Data</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="rounded border overflow-auto max-h-[600px] [&_*]:break-words">
                  <JsonView
                    value={sanitizeForJsonView(item.input)}
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
          )}

          {orderedNodeIds.length === 0 ? (
            <Card>
              <CardContent className="py-8 text-sm text-muted-foreground text-center">
                No node execution details are available for this item.
              </CardContent>
            </Card>
          ) : (
            orderedNodeIds.map((nodeId) => {
              const nodeConfig = graph?.spec.nodes.find(n => n.id === nodeId)
              const nodeType = nodeConfig?.type || 'Unknown'
              const friendlyName =
                (nodeConfig?.params as any)?.name ||
                (nodeConfig?.params as any)?.label ||
                nodeType

              const output = getNodeOutputById(rawOutputs, nodeId)
              const logs = nodeLogs[nodeId] ?? []

              return (
                <Card key={nodeId}>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <span>{friendlyName}</span>
                      <Badge variant="secondary" className="font-mono text-[10px]">
                        {nodeId}
                      </Badge>
                      <span className="text-xs uppercase tracking-wide text-muted-foreground">
                        {nodeType}
                      </span>
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="grid gap-4 md:grid-cols-2">
                      <div className="space-y-3">
                        <div className="text-sm font-semibold">Output</div>
                        {output ? (
                          <div className="rounded border overflow-auto max-h-64 [&_*]:break-words">
                            <JsonView
                              value={sanitizeForJsonView(output)}
                              style={{
                                backgroundColor: 'transparent',
                                fontSize: '0.75rem',
                              }}
                              collapsed={false}
                              displayDataTypes={false}
                              displayObjectSize={false}
                            />
                          </div>
                        ) : (
                          <p className="text-sm text-muted-foreground">
                            This node did not produce any output.
                          </p>
                        )}
                      </div>
                      <div className="space-y-3">
                        <div className="text-sm font-semibold">Logs</div>
                        {logs.length > 0 ? (
                          <div className="bg-muted rounded p-3 max-h-64 overflow-auto text-xs font-mono space-y-2">
                            {logs.map((line, idx) => (
                              <div key={idx}>{line}</div>
                            ))}
                          </div>
                        ) : (
                          <p className="text-sm text-muted-foreground">
                            No logs were recorded for this node.
                          </p>
                        )}
                      </div>
                    </div>
                  </CardContent>
                </Card>
              )
            })
          )}
        </TabsContent>
      </Tabs>
    </div>
  )
}

