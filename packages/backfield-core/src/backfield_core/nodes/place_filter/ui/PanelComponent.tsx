import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

interface PlaceFilterPanelProps {
  node: any
  onChange?: (text: string) => void
  onRun?: () => void
  running?: boolean
  currentRun?: any
  editMode?: boolean
  setNodes?: (nodes: any) => void
}

export default function PlaceFilterPanel({
  node,
  onChange,
  onRun,
  running,
  currentRun,
  editMode,
  setNodes
}: PlaceFilterPanelProps) {
  const nodeOutput = currentRun?.node_outputs?.[node.id]
  const latestData = nodeOutput || null

  const modelOptions =
    nodeMetadata.availableModels && nodeMetadata.availableModels.length > 0
      ? nodeMetadata.availableModels
      : [{ value: 'gpt-5', label: 'GPT-5' }]

  const defaultModel = nodeMetadata.defaultParams?.model || 'gpt-5'

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
          <Label className="text-sm font-medium">Prompt placeholders</Label>
          <p className="text-sm text-muted-foreground mt-1">
            Use tokens to pull fields from the merged upstream JSON (same behavior as the original Flowbuilder node):
          </p>
          <ul className="list-disc list-inside text-xs mt-2 space-y-1 text-muted-foreground">
            <li>
              <code className="bg-muted px-1 rounded">{'{text}'}</code> — article text
            </li>
            <li>
              <code className="bg-muted px-1 rounded">{'{locations}'}</code> — extracted locations array
            </li>
            <li>
              <code className="bg-muted px-1 rounded">{'{url}'}</code>,{' '}
              <code className="bg-muted px-1 rounded">{'{raw}'}</code> — other paths as supported by the runtime
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
                value={node.data.model || defaultModel}
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
                <span className="font-medium text-xs">{node.data.model || defaultModel}</span>
              </div>
            )}
          </div>

          <div className="space-y-1">
            <Label className="text-xs text-muted-foreground">Prompt</Label>
            {editMode && setNodes ? (
              <textarea
                value={node.data.prompt ?? nodeMetadata.defaultParams?.prompt ?? ''}
                onChange={(e) => {
                  setNodes((nds: any[]) =>
                    nds.map((n: any) =>
                      n.id === node.id ? { ...n, data: { ...n.data, prompt: e.target.value } } : n
                    )
                  )
                }}
                placeholder="Leave empty to use the default filter prompt from prompts/filter.md"
                className="w-full min-h-[200px] px-3 py-2 text-xs border border-input bg-background rounded-md focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 font-mono"
              />
            ) : (
              <div className="p-2 bg-muted rounded max-h-48 overflow-y-auto">
                <pre className="text-xs whitespace-pre-wrap font-mono">
                  {(node.data.prompt ?? nodeMetadata.defaultParams?.prompt) || 'Using default prompt file'}
                </pre>
              </div>
            )}
          </div>

          <div className="space-y-1">
            <Label className="text-xs text-muted-foreground">Output format (JSON example)</Label>
            {editMode && setNodes ? (
              <textarea
                value={node.data.json_format ?? nodeMetadata.defaultParams?.json_format ?? ''}
                onChange={(e) => {
                  setNodes((nds: any[]) =>
                    nds.map((n: any) =>
                      n.id === node.id ? { ...n, data: { ...n.data, json_format: e.target.value } } : n
                    )
                  )
                }}
                placeholder='[{"index":0,"relevant":true,"reason":""}]'
                className="w-full min-h-[120px] px-3 py-2 text-xs border border-input bg-background rounded-md focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 font-mono"
              />
            ) : (
              <div className="p-2 bg-muted rounded border border-input max-h-48 overflow-y-auto">
                <pre className="text-xs whitespace-pre-wrap font-mono text-muted-foreground">
                  {node.data.json_format ?? nodeMetadata.defaultParams?.json_format ?? ''}
                </pre>
              </div>
            )}
            <p className="text-xs text-muted-foreground mt-1">
              Braces in this block are escaped automatically when appended to the prompt.
            </p>
          </div>
        </div>
      </div>

      {latestData?.locations && (
        <div className="pt-4 border-t">
          <Label className="text-sm font-medium">Latest run</Label>
          <p className="text-xs text-muted-foreground mt-2">
            Locations kept: {latestData.locations.length}
          </p>
        </div>
      )}
    </>
  )
}
