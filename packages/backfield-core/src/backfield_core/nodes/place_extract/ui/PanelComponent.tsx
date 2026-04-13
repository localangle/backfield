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

function formatSamplePlaceTitle(location: {
  location?: unknown
  original_text?: string
}): string {
  const loc = location.location
  if (typeof loc === 'string') {
    return loc
  }
  if (loc && typeof loc === 'object' && 'full' in loc) {
    const full = (loc as { full?: unknown }).full
    if (typeof full === 'string' && full.length > 0) {
      return full
    }
  }
  return typeof location.original_text === 'string' ? location.original_text : ''
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
  const nodeOutput = currentRun?.node_outputs?.[node.id]
  const latestData = nodeOutput || null

  const modelOptions =
    nodeMetadata.availableModels && nodeMetadata.availableModels.length > 0
      ? nodeMetadata.availableModels
      : [{ value: 'gpt-4o-mini', label: 'GPT-4o Mini' }]

  return (
    <>
      <div className="space-y-4">
        <div>
          <Label className="text-sm font-medium">About</Label>
          <p className="text-sm text-muted-foreground mt-1">{nodeMetadata.description}</p>
          {nodeMetadata.dependencyHelperText ? (
            <p className="text-sm text-muted-foreground mt-2 border-l-2 border-muted pl-3">
              {nodeMetadata.dependencyHelperText}
            </p>
          ) : null}
        </div>

        <div>
          <Label className="text-sm font-medium">Input placeholders</Label>
          <p className="text-sm text-muted-foreground mt-1">
            Pull fields from upstream JSON into the prompt using these tokens (same behavior as the original
            Flowbuilder Place Extract node):
          </p>
          <ul className="list-disc list-inside text-xs mt-2 space-y-1 text-muted-foreground">
            <li>
              <code className="bg-muted px-1 rounded">{'{text}'}</code> — plain text or the <code className="bg-muted px-1 rounded">text</code>{' '}
              field from JSON input
            </li>
            <li>
              <code className="bg-muted px-1 rounded">{'{url}'}</code> — <code className="bg-muted px-1 rounded">url</code> field
            </li>
            <li>
              <code className="bg-muted px-1 rounded">{'{results.images}'}</code> — nested paths (e.g.{' '}
              <code className="bg-muted px-1 rounded">results.images</code>)
            </li>
            <li>
              <code className="bg-muted px-1 rounded">{'{results.caption}'}</code> — one field from each item in an array
            </li>
            <li>
              <code className="bg-muted px-1 rounded">{'{results.caption, id}'}</code> — multiple fields per array element
            </li>
            <li>
              <code className="bg-muted px-1 rounded">{'{raw}'}</code> — entire input object as JSON
            </li>
          </ul>
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
                value={node.data.model || nodeMetadata.defaultParams?.model || 'gpt-4o-mini'}
                onValueChange={(value) => {
                  setNodes((nds: any[]) =>
                    nds.map((n: any) =>
                      n.id === node.id ? { ...n, data: { ...n.data, model: value } } : n
                    )
                  )
                }}
              >
                <SelectTrigger className="h-8 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {modelOptions.map((model) => (
                    <SelectItem key={model.value} value={model.value}>
                      {model.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : (
              <div className="flex justify-between items-center p-2 bg-muted rounded">
                <span className="text-muted-foreground">Model</span>
                <span className="font-medium text-xs">
                  {node.data.model || nodeMetadata.defaultParams?.model || 'gpt-4o-mini'}
                </span>
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
            Tune extraction instructions. Placeholders:{' '}
            <code className="bg-muted px-1 rounded">{'{text}'}</code>,{' '}
            <code className="bg-muted px-1 rounded">{'{url}'}</code>,{' '}
            <code className="bg-muted px-1 rounded">{'{results.images}'}</code>,{' '}
            <code className="bg-muted px-1 rounded">{'{results.caption}'}</code>,{' '}
            <code className="bg-muted px-1 rounded">{'{results.caption, id}'}</code>,{' '}
            <code className="bg-muted px-1 rounded">{'{raw}'}</code>.
          </p>
        </div>

        <div className="pt-2">
          <Label className="text-sm font-medium">Output format</Label>
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
                {node.data?.json_format ||
                  nodeMetadata.defaultParams?.json_format ||
                  '{ "locations": [] }'}
              </pre>
            </div>
          )}
          <p className="text-xs text-muted-foreground mt-1">
            Example JSON shape the model should return. Braces are escaped when this is merged into the prompt.
          </p>
        </div>
      </div>

      {latestData && latestData.locations && (
        <div className="pt-4 border-t">
          <Label className="text-sm font-medium">Latest run</Label>
          <div className="mt-2 space-y-2">
            <div className="text-xs text-muted-foreground">
              <div>Places found: {latestData.locations.length}</div>
            </div>

            {latestData.locations.length > 0 && (
              <div>
                <Label className="text-xs font-medium">Sample places</Label>
                <div className="mt-1 space-y-1 max-h-32 overflow-y-auto">
                  {latestData.locations.slice(0, 3).map((location: any, index: number) => (
                    <div key={index} className="text-xs p-2 bg-muted rounded">
                      <div className="font-medium">{formatSamplePlaceTitle(location)}</div>
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
