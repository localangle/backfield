// Auto-injected metadata for PlaceExtract
const nodeMetadata = {
  "type": "PlaceExtract",
  "label": "Place Extract",
  "icon": "MapPin",
  "color": "bg-purple-500",
  "description": "Extract place-like mentions (starter: City, ST heuristic).",
  "category": "extraction",
  "inputs": [
    {
      "id": "text",
      "label": "Text",
      "type": "string",
      "required": true
    }
  ],
  "outputs": [
    {
      "id": "locations",
      "label": "Locations",
      "type": "array"
    }
  ],
  "defaultParams": {}
};

import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

interface PlaceExtractPanelProps {
  node: any
  onChange?: (text: string) => void
  onRun?: () => void
  running?: boolean
  currentRun?: any
  editMode?: boolean
  setNodes?: (nodes: any) => void
}

export default function PlaceExtractPanel({
  node,
  onChange,
  onRun,
  running,
  currentRun,
  editMode,
  setNodes
}: PlaceExtractPanelProps) {
  // Debug: Log what we're getting
  if (currentRun?.node_outputs) {
    console.log('PlaceExtract Panel Debug:', {
      nodeId: node.id,
      nodeType: node.type,
      nodeOutputs: currentRun.node_outputs,
      specificNodeOutput: currentRun.node_outputs[node.id],
      allNodeIds: Object.keys(currentRun.node_outputs)
    })
  }
  
  // Get latest run data - only show if we have specific node output
  const nodeOutput = currentRun?.node_outputs?.[node.id]
  const latestData = nodeOutput || null

  return (
    <>
      <div className="space-y-3">
        <div>
          <Label className="text-sm font-medium">Description</Label>
          <p className="text-sm text-muted-foreground mt-1">
            This node uses an LLM to process JSON according to your custom prompt and returns structured place data. Use JSON path placeholders in your prompt to extract specific fields:
            <ul className="list-disc list-inside text-xs mt-2 space-y-1">
              <li><code className="bg-muted px-1 rounded">{'{text}'}</code> - extracts the text field</li>
              <li><code className="bg-muted px-1 rounded">{'{url}'}</code> - extracts the url field</li>
              <li><code className="bg-muted px-1 rounded">{'{results.images}'}</code> - extracts nested results.images object/array</li>
              <li><code className="bg-muted px-1 rounded">{'{results.caption}'}</code> - extracts only caption field from array elements</li>
              <li><code className="bg-muted px-1 rounded">{'{results.caption, id}'}</code> - extracts multiple fields from array elements</li>
              <li><code className="bg-muted px-1 rounded">{'{raw}'}</code> - passes entire input JSON</li>
            </ul>
          </p>
        </div>
      </div>

      <div className="pt-4 border-t">
        <div>
          <Label className="text-sm font-medium">Parameters</Label>
        </div>
        
        <div className="space-y-2 text-sm mt-2">
          <div className="space-y-1">
            <Label className="text-xs text-muted-foreground">Model</Label>
            {editMode && setNodes ? (
              <Select
                value={node.data.model || 'gpt-4o-mini'}
                onValueChange={(value) => {
                  setNodes((nds: any[]) =>
                    nds.map((n: any) =>
                      n.id === node.id
                        ? { ...n, data: { ...n.data, model: value } }
                        : n
                    )
                  )
                }}
              >
                <SelectTrigger className="h-8 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {nodeMetadata.availableModels?.map((model) => (
                    <SelectItem key={model.value} value={model.value}>
                      {model.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : (
              <div className="flex justify-between items-center p-2 bg-muted rounded">
                <span className="text-muted-foreground">Model</span>
                <span className="font-medium text-xs">{node.data.model || 'gpt-4o-mini'}</span>
              </div>
            )}
          </div>
        </div>

        <div className="pt-2">
          <Label className="text-sm font-medium">Prompt</Label>
          {editMode && setNodes ? (
            <Textarea
              value={node.data?.prompt || nodeMetadata.defaultParams?.prompt || ''}
              onChange={(e) => {
                setNodes((nds: any[]) =>
                  nds.map((n: any) =>
                    n.id === node.id
                      ? { ...n, data: { ...n.data, prompt: e.target.value } }
                      : n
                  )
                )
              }}
              placeholder="Enter custom prompt"
              className="mt-2 min-h-[200px] px-3 py-2 text-xs border border-input bg-background rounded-md focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 font-mono"
            />
          ) : (
            <div className="mt-2 p-2 bg-muted rounded max-h-48 overflow-y-auto">
              <pre className="text-xs whitespace-pre-wrap font-mono">
                {node.data?.prompt || nodeMetadata.defaultParams?.prompt || 'Using default prompt'}
              </pre>
            </div>
          )}
          <p className="text-xs text-muted-foreground mt-1">
            Customize the prompt for extracting locations. Use placeholders like {`{text}`}, {`{location}`}, {`{url}`}, {`{results.images}`}, {`{results.caption}`}, {`{results.caption, id}`}, {`{raw}`}.
          </p>
        </div>

        <div className="pt-2">
          <Label className="text-sm font-medium">Output Format</Label>
          {editMode && setNodes ? (
            <Textarea
              value={node.data?.json_format || nodeMetadata.defaultParams?.json_format || ''}
              onChange={(e) => {
                setNodes((nds: any[]) =>
                  nds.map((n: any) =>
                    n.id === node.id
                      ? { ...n, data: { ...n.data, json_format: e.target.value } }
                      : n
                  )
                )
              }}
              placeholder='{ "locations": [] }'
              className="mt-2 min-h-[100px] px-3 py-2 text-xs border border-input bg-background rounded-md focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 font-mono"
            />
          ) : (
            <div className="mt-2 p-2 bg-muted rounded max-h-48 overflow-y-auto">
              <pre className="text-xs whitespace-pre-wrap font-mono">
                {node.data?.json_format || nodeMetadata.defaultParams?.json_format || '{ "locations": [] }'}
              </pre>
            </div>
          )}
          <p className="text-xs text-muted-foreground mt-1">
            Example output JSON. Braces are escaped automatically in the prompt.
          </p>
        </div>
      </div>

      {latestData && latestData.locations && (
        <div className="pt-4 border-t">
          <Label className="text-sm font-medium">Latest Run</Label>
          <div className="mt-2 space-y-2">
            <div className="text-xs text-muted-foreground">
              <div>Places found: {latestData.locations.length}</div>
            </div>
            
            {latestData.locations.length > 0 && (
              <div>
                <Label className="text-xs font-medium">Sample Places:</Label>
                <div className="mt-1 space-y-1 max-h-32 overflow-y-auto">
                  {latestData.locations.slice(0, 3).map((location: any, index: number) => (
                    <div key={index} className="text-xs p-2 bg-muted rounded">
                      <div className="font-medium">{location.location?.full || location.original_text}</div>
                      {location.description && (
                        <div className="text-muted-foreground">{location.description}</div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  )
}
