import { X, Play, Loader2, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'
import type { Run } from '@/lib/api'
import { Suspense } from 'react'
import { panelComponents } from '@/nodes/registry'

interface NodePanelProps {
  selectedNode: any
  onClose: () => void
  onTextChange?: (text: string) => void
  onRun?: () => void
  onDelete?: (nodeId: string) => void
  running?: boolean
  currentRun?: Run | null
  editMode?: boolean
  setNodes?: (nodes: any) => void
  showModal?: (config: {
    title: string
    description: string
    type: 'info' | 'warning' | 'error' | 'success'
    confirmText?: string
    cancelText?: string
    onConfirm: () => void
    onCancel?: () => void
  }) => void
}

export default function NodePanel({
  selectedNode,
  onClose,
  onTextChange,
  onRun,
  onDelete,
  running,
  currentRun,
  editMode,
  setNodes,
  showModal,
}: NodePanelProps) {
  if (!selectedNode) return null
  
  const handleDelete = () => {
    if (showModal) {
      showModal({
        title: 'Delete Node',
        description: `Are you sure you want to delete the ${selectedNode.type} node? This action cannot be undone.`,
        type: 'warning',
        confirmText: 'Delete',
        cancelText: 'Cancel',
        onConfirm: () => onDelete?.(selectedNode.id),
      })
    } else {
      // Fallback to confirm if showModal is not provided
      if (confirm(`Delete ${selectedNode.type} node?`)) {
        onDelete?.(selectedNode.id)
      }
    }
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'succeeded':
        return 'bg-green-500'
      case 'failed':
        return 'bg-red-500'
      case 'running':
        return 'bg-blue-500'
      default:
        return 'bg-gray-500'
    }
  }

  return (
    <div className="absolute top-0 right-0 h-full w-96 bg-background/95 backdrop-blur-sm border-l shadow-lg flex flex-col z-10 slide-in-from-right">
      <div className="flex items-center justify-between p-4 border-b">
        <div>
          <h3 className="font-semibold text-lg">{selectedNode.type}</h3>
        </div>
        <div className="flex gap-1">
          {editMode && onDelete && (
            <Button variant="ghost" size="icon" onClick={handleDelete} title="Delete node">
              <Trash2 className="h-4 w-4 text-destructive" />
            </Button>
          )}
          <Button variant="ghost" size="icon" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        <Suspense fallback={<div>Loading...</div>}>
          {(() => {
            const PanelComponent = panelComponents[selectedNode.type as keyof typeof panelComponents]
            if (PanelComponent) {
              return (
                <PanelComponent
                  node={selectedNode}
                  onChange={onTextChange}
                  onRun={onRun}
                  running={running}
                  currentRun={currentRun}
                  editMode={editMode}
                  setNodes={setNodes}
                />
              )
            }
            return <div>Unknown node type: {selectedNode.type}</div>
          })()}
        </Suspense>

        {/* Legacy conditional logic - to be removed after migration */}
        {false && selectedNode.type === 'TextInput' && (
          <>
            <div className="space-y-2">
              <Label htmlFor="node-text">Input Text</Label>
              <Textarea
                id="node-text"
                value={selectedNode.data.text || ''}
                onChange={(e) => onTextChange?.(e.target.value)}
                placeholder="Enter article text..."
                className="min-h-[300px]"
              />
              <p className="text-xs text-muted-foreground">
                This text will be passed to connected downstream nodes.
              </p>
            </div>

              <Button
                onClick={onRun}
                disabled={running || !selectedNode.data.text?.trim()}
                className="w-full"
                size="lg"
              >
                {running ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Running Flow...
                  </>
                ) : (
                  <>
                    <Play className="mr-2 h-4 w-4" />
                    Run Flow
                  </>
                )}
              </Button>
          </>
        )}

        {false && selectedNode.type === 'Embed' && (
          <>
            <div className="space-y-3">
              <div>
                <Label className="text-sm font-medium">Parameters</Label>
              </div>
              
              <div className="space-y-2 text-sm">
                <div className="flex justify-between items-center p-2 bg-muted rounded">
                  <span className="text-muted-foreground">Model</span>
                  <span className="font-medium text-xs">{selectedNode.data.model || 'text-embedding-3-small'}</span>
                </div>
                
                <div className="flex justify-between items-center p-2 bg-muted rounded">
                  <span className="text-muted-foreground">Dimensions</span>
                  <span className="font-medium">{selectedNode.data.dimensions || 1536}</span>
                </div>
              </div>
            </div>

            <div className="pt-4 border-t">
              <p className="text-sm text-muted-foreground">
                This node converts text into a vector embedding with {selectedNode.data.dimensions || 1536} dimensions using OpenAI's embedding models.
              </p>
            </div>
          </>
        )}

        {false && false && (
          <>
            <div className="space-y-3">
              <div>
                <Label className="text-sm font-medium">Parameters</Label>
              </div>
              
              <div className="space-y-2 text-sm">
                <div className="flex justify-between items-center p-2 bg-muted rounded">
                  <span className="text-muted-foreground">Top K</span>
                  <span className="font-medium">{selectedNode.data.top_k || 3}</span>
                </div>
                
                <div className="flex justify-between items-center p-2 bg-muted rounded">
                  <span className="text-muted-foreground">Model</span>
                  <span className="font-medium text-xs">{selectedNode.data.model || 'gpt-4o-mini'}</span>
                </div>
              </div>

              <div className="pt-2">
                <Label className="text-sm font-medium">Label Set</Label>
                <div className="mt-2 flex flex-wrap gap-1">
                  {[
                    'crime', 'politics', 'education', 'sports', 'business',
                    'weather', 'health', 'arts_culture', 'transportation'
                  ].map(label => (
                    <Badge key={label} variant="secondary" className="text-xs">
                      {label.replace('_', ' ')}
                    </Badge>
                  ))}
                </div>
              </div>
            </div>

            <div className="pt-4 border-t">
              <p className="text-sm text-muted-foreground">
                This node classifies article text using an LLM and returns the top {selectedNode.data.top_k || 3} most relevant categories.
              </p>
            </div>
          </>
        )}

        {false && selectedNode.type === 'LLMEnrich' && (
          <>
            <div className="space-y-3">
              <div>
                <Label className="text-sm font-medium">Parameters</Label>
              </div>
              
              <div className="space-y-2 text-sm">
                <div className="flex justify-between items-center p-2 bg-muted rounded">
                  <span className="text-muted-foreground">Model</span>
                  <span className="font-medium text-xs">{selectedNode.data.model || 'gpt-4o-mini'}</span>
                </div>
              </div>

              <div className="pt-2">
                <Label className="text-sm font-medium">Prompt</Label>
                {editMode && setNodes ? (
                  <Textarea
                    value={selectedNode.data.prompt || ''}
                    onChange={(e) => {
                      setNodes((nds: any[]) =>
                        nds.map((n: any) =>
                          n.id === selectedNode.id
                            ? { ...n, data: { ...n.data, prompt: e.target.value } }
                            : n
                        )
                      )
                    }}
                    placeholder="Enter your prompt here. Use {text} to reference the input text."
                    className="mt-2 min-h-[80px] text-xs font-mono"
                  />
                ) : (
                  <div className="mt-2 p-3 bg-muted rounded-lg">
                    <p className="text-xs text-muted-foreground whitespace-pre-wrap">
                      {selectedNode.data.prompt || 'No prompt set'}
                    </p>
                  </div>
                )}
              </div>

              <div className="pt-2">
                <Label className="text-sm font-medium">JSON Format</Label>
                {editMode && setNodes ? (
                  <Textarea
                    value={selectedNode.data.json_format || ''}
                    onChange={(e) => {
                      setNodes((nds: any[]) =>
                        nds.map((n: any) =>
                          n.id === selectedNode.id
                            ? { ...n, data: { ...n.data, json_format: e.target.value } }
                            : n
                        )
                      )
                    }}
                    placeholder='{"key": "value", "example": "format"}'
                    className="mt-2 min-h-[60px] text-xs font-mono"
                  />
                ) : (
                  <div className="mt-2 p-3 bg-muted rounded-lg">
                    <p className="text-xs text-muted-foreground font-mono">
                      {selectedNode.data.json_format || '{}'}
                    </p>
                  </div>
                )}
              </div>
            </div>

            <div className="pt-4 border-t">
              <p className="text-sm text-muted-foreground">
                This node uses an LLM to process text according to your custom prompt and returns structured JSON data.
                Use {'{text}'} in your prompt to reference the input text.
              </p>
            </div>
          </>
        )}

        {false && selectedNode.type === 'Output' && (
          <>
            <div className="space-y-3">
              <div className="p-4 bg-muted rounded-lg">
                <p className="text-sm text-muted-foreground">
                  This node consolidates data from all upstream nodes into a single output.
                </p>
              </div>
              
              <div className="pt-2">
                <Label className="text-sm font-medium">Behavior</Label>
                <div className="mt-2 space-y-2 text-xs text-muted-foreground">
                  <p>• Accepts any number of inputs</p>
                  <p>• Merges all fields into one object</p>
                  <p>• Waits for all upstream nodes to complete</p>
                  <p>• Returns consolidated data structure</p>
                </div>
              </div>
            </div>

            <div className="pt-4 border-t">
              <p className="text-sm text-muted-foreground">
                Perfect for combining results from parallel enrich nodes (Embed, etc.)
              </p>
            </div>
          </>
        )}

        {currentRun && false && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Latest Run</CardTitle>
              <CardDescription>
                Run #{currentRun.id} • Status: {currentRun.status}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center gap-2">
                <div className={`h-2 w-2 rounded-full ${getStatusColor(currentRun.status)}`} />
                <span className="text-sm font-medium capitalize">{currentRun.status}</span>
              </div>

              {currentRun.status === 'running' && (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Processing...
                </div>
              )}

              {currentRun.status === 'failed' && currentRun.error && (
                <div className="p-3 bg-destructive/10 border border-destructive rounded-lg">
                  <p className="text-xs font-medium text-destructive">Error</p>
                  <p className="text-xs mt-1">{currentRun.error}</p>
                </div>
              )}

              {currentRun.status === 'succeeded' && (
                <div className="space-y-3">
                  <div>
                    <h4 className="text-sm font-medium mb-2">Node Output</h4>
                    
                    {/* Show individual node output if available */}
                    {currentRun.node_outputs && currentRun.node_outputs[selectedNode.id] ? (
                      <div className="space-y-3">
                        <div className="p-3 bg-muted/50 rounded-lg border">
                          <p className="text-xs font-medium mb-2">Node: {selectedNode.type}</p>
                          <div className="space-y-1 text-xs">
                            {Object.keys(currentRun.node_outputs[selectedNode.id]).map((key) => (
                              <div key={key} className="flex items-center gap-2">
                                <Badge variant="outline" className="text-xs">
                                  {key}
                                </Badge>
                                <span className="text-muted-foreground">
                                  {Array.isArray(currentRun.node_outputs?.[selectedNode.id]?.[key]) 
                                    ? `Array[${currentRun.node_outputs?.[selectedNode.id]?.[key]?.length}]`
                                    : typeof currentRun.node_outputs?.[selectedNode.id]?.[key]}
                                </span>
                              </div>
                            ))}
                          </div>
                        </div>
                        
                        {/* Show specific node output details */}
                        {currentRun.node_outputs?.[selectedNode.id]?.labels && (
                          <div>
                            <p className="text-xs font-medium mb-1">Classifications</p>
                            <div className="space-y-1">
                              {currentRun.node_outputs[selectedNode.id].labels.slice(0, 3).map((label: any, idx: number) => (
                                <div key={idx} className="flex justify-between text-xs">
                                  <span className="capitalize">{label.label?.replace('_', ' ')}</span>
                                  <span>{((label.score || 0) * 100).toFixed(0)}%</span>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                        
                        {currentRun.node_outputs?.[selectedNode.id]?.embedding && (
                          <div>
                            <p className="text-xs font-medium mb-1">Embedding</p>
                            <div className="flex justify-between text-xs p-2 bg-muted rounded">
                              <span className="text-muted-foreground">Dimensions</span>
                              <span className="font-medium">{currentRun.node_outputs[selectedNode.id].dimensions || currentRun.node_outputs[selectedNode.id].embedding.length}</span>
                            </div>
                          </div>
                        )}

                        {currentRun.node_outputs?.[selectedNode.id]?.enriched_data && (
                          <div>
                            <p className="text-xs font-medium mb-1">LLM Enrichment</p>
                            <div className="p-2 bg-muted rounded">
                              <p className="text-xs text-muted-foreground mb-1">Custom JSON data:</p>
                              <code className="text-xs font-mono">
                                {JSON.stringify(currentRun.node_outputs[selectedNode.id].enriched_data, null, 2).substring(0, 100)}
                                {JSON.stringify(currentRun.node_outputs[selectedNode.id].enriched_data, null, 2).length > 100 ? '...' : ''}
                              </code>
                            </div>
                          </div>
                        )}

                        {currentRun.node_outputs?.[selectedNode.id]?.locations && (
                          <div>
                            <p className="text-xs font-medium mb-1">Locations</p>
                            <div className="space-y-1">
                              {currentRun.node_outputs[selectedNode.id].locations.slice(0, 3).map((location: any, idx: number) => (
                                <div key={idx} className="text-xs p-2 bg-muted rounded">
                                  <div className="font-medium">{location.location?.full || location.original_text}</div>
                                  <div className="text-muted-foreground">{location.description}</div>
                                </div>
                              ))}
                              {currentRun.node_outputs[selectedNode.id].locations.length > 3 && (
                                <div className="text-xs text-muted-foreground">
                                  ... and {currentRun.node_outputs[selectedNode.id].locations.length - 3} more
                                </div>
                              )}
                            </div>
                          </div>
                        )}
                      </div>
                    ) : currentRun.output && currentRun.output.data ? (
                      /* Fallback to consolidated output if node-specific output not available */
                      <div className="space-y-3">
                        <div className="p-3 bg-muted/50 rounded-lg border">
                          <p className="text-xs font-medium mb-2">Consolidated Data (Fallback)</p>
                          <div className="space-y-1 text-xs">
                            {Object.keys(currentRun.output.data).map((key) => (
                              <div key={key} className="flex items-center gap-2">
                                <Badge variant="outline" className="text-xs">
                                  {key}
                                </Badge>
                                <span className="text-muted-foreground">
                                  {Array.isArray(currentRun.output?.data?.[key]) 
                                    ? `Array[${currentRun.output?.data?.[key]?.length}]`
                                    : typeof currentRun.output?.data?.[key]}
                                </span>
                              </div>
                            ))}
                          </div>
                        </div>
                      </div>
                    ) : (
                      <div className="p-3 bg-muted/50 rounded-lg border">
                        <p className="text-xs text-muted-foreground">No output data available</p>
                      </div>
                    )}
                    
                    {/* Classification results (when not consolidated) */}
                    {currentRun.output.labels && !currentRun.output.data && (
                      <div className="space-y-2">
                        {currentRun.output.labels.map((label: any, idx: number) => (
                          <div key={idx} className="space-y-1">
                            <div className="flex justify-between text-xs">
                              <span className="font-medium capitalize">{label.label.replace('_', ' ')}</span>
                              <span>{(label.score * 100).toFixed(0)}%</span>
                            </div>
                            <div className="w-full bg-secondary rounded-full h-1.5">
                              <div
                                className="bg-primary h-1.5 rounded-full transition-all"
                                style={{ width: `${label.score * 100}%` }}
                              />
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                    
                    {/* Embedding results (when not consolidated) */}
                    {currentRun.output.embedding && !currentRun.output.data && (
                      <div className="space-y-2">
                        <div className="flex justify-between items-center p-2 bg-muted rounded">
                          <span className="text-xs text-muted-foreground">Vector Length</span>
                          <span className="text-xs font-medium">{currentRun.output.dimensions || currentRun.output.embedding.length}</span>
                        </div>
                        <div className="flex justify-between items-center p-2 bg-muted rounded">
                          <span className="text-xs text-muted-foreground">Model</span>
                          <span className="text-xs font-medium">{currentRun.output.model || 'unknown'}</span>
                        </div>
                        <div className="p-2 bg-muted rounded">
                          <p className="text-xs text-muted-foreground mb-1">First 5 dimensions:</p>
                          <code className="text-xs font-mono">
                            [{currentRun.output.embedding.slice(0, 5).map((v: number) => v.toFixed(4)).join(', ')}...]
                          </code>
                        </div>
                      </div>
                    )}

                    {currentRun.output.enriched_data && !currentRun.output.data && (
                      <div className="space-y-2">
                        <div className="p-2 bg-muted rounded">
                          <p className="text-xs text-muted-foreground mb-1">LLM Enrichment:</p>
                          <code className="text-xs font-mono">
                            {JSON.stringify(currentRun.output?.enriched_data, null, 2).substring(0, 150)}
                            {JSON.stringify(currentRun.output?.enriched_data, null, 2).length > 150 ? '...' : ''}
                          </code>
                        </div>
                      </div>
                    )}
                  </div>

                  <details className="text-xs">
                    <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
                      View raw JSON
                    </summary>
                    <pre className="mt-2 p-2 bg-muted rounded text-xs overflow-auto max-h-40">
                      {currentRun.node_outputs && currentRun.node_outputs[selectedNode.id] 
                        ? JSON.stringify(currentRun.node_outputs[selectedNode.id], null, 2)
                        : JSON.stringify(currentRun.output, null, 2)}
                    </pre>
                  </details>
                </div>
              )}
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  )
}

