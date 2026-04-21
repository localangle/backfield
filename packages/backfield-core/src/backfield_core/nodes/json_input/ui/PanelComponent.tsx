import { useState, useEffect } from 'react'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { getNodeOutputById, type NodeOutputLookupSpec } from '@/lib/nodeOutputs'

interface JSONInputPanelProps {
  node: any
  onChange?: (jsonData: unknown) => void
  onRun?: () => void
  running?: boolean
  currentRun?: any
  editMode?: boolean
  setNodes?: (nodes: any) => void
  nodeOutputLookupSpec?: NodeOutputLookupSpec | null
}

export default function JSONInputPanel({
  node,
  currentRun,
  editMode,
  setNodes,
  nodeOutputLookupSpec,
}: JSONInputPanelProps) {
  const [jsonText, setJsonText] = useState('')
  const [jsonError, setJsonError] = useState('')

  useEffect(() => {
    try {
      const base = { ...(node.data || {}), text: (node.data?.text as string) ?? '' }
      delete (base as { onChange?: unknown }).onChange
      setJsonText(JSON.stringify(base, null, 2))
      setJsonError('')
    } catch {
      setJsonText('{\n  "text": ""\n}')
    }
  }, [node.id])

  const handleJsonChange = (value: string) => {
    setJsonText(value)

    try {
      const parsed = JSON.parse(value) as unknown
      if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
        setJsonError('JSON must be an object')
        return
      }
      const rec = parsed as Record<string, unknown>
      if (!('text' in rec)) {
        setJsonError('JSON must include a "text" field')
        return
      }
      if (typeof rec.text !== 'string' || !rec.text.trim()) {
        setJsonError('"text" must be a non-empty string')
        return
      }

      setJsonError('')

      if (setNodes) {
        setNodes((nds: any[]) =>
          nds.map((n: any) => (n.id === node.id ? { ...n, data: parsed } : n)),
        )
      }
    } catch {
      setJsonError('Invalid JSON syntax')
    }
  }

  const isDisabled = !(editMode && setNodes)

  const rawOutputs = currentRun?.node_outputs as Record<string, unknown> | undefined
  const slice = rawOutputs
    ? (getNodeOutputById(rawOutputs, node.id, nodeOutputLookupSpec ?? undefined) as
        | Record<string, unknown>
        | undefined)
    : undefined

  return (
    <>
      <div className="space-y-3">
        <div>
          <Label className="text-sm font-medium">Description</Label>
          <p className="text-sm text-muted-foreground mt-1">
            Structured JSON for the flow. The <span className="font-mono">&quot;text&quot;</span>{' '}
            field is required for downstream text processing. Any other top-level fields (for
            example <span className="font-mono">headline</span>,{' '}
            <span className="font-mono">url</span>, nested objects) are passed through so prompts
            can reference them with placeholders like{' '}
            <span className="font-mono">{'{headline}'}</span>.
          </p>
        </div>
      </div>

      <div className="pt-4 border-t">
        <div>
          <Label className="text-sm font-medium">Parameters</Label>
        </div>

        <div className="space-y-2 mt-2">
          <div>
            <Label htmlFor="node-json" className="text-xs text-muted-foreground">
              JSON data (must include &quot;text&quot;)
            </Label>
            <Textarea
              id="node-json"
              value={jsonText}
              onChange={(e) => handleJsonChange(e.target.value)}
              placeholder={`{\n  "text": "Your text here...",\n  "headline": "Optional headline"\n}`}
              className="min-h-[300px] mt-1 font-mono text-xs"
              disabled={isDisabled}
            />
            {jsonError && <p className="text-xs text-red-500 mt-1">{jsonError}</p>}
            <p className="text-xs text-muted-foreground mt-1">
              Example:{' '}
              <span className="font-mono">
                {'{'}&quot;text&quot;: &quot;Article…&quot;, &quot;headline&quot;: &quot;Title&quot;
                {'}'}
              </span>
            </p>
          </div>
        </div>
      </div>

      {slice && typeof slice.text === 'string' && (
        <div className="pt-4 border-t">
          <Label className="text-sm font-medium">Latest run</Label>
          <div className="mt-2 space-y-2">
            <div className="text-xs text-muted-foreground">
              Fields in output: {Object.keys(slice).length}
            </div>
            <div>
              <Label className="text-xs font-medium">Output preview</Label>
              <div className="text-xs font-mono p-2 bg-muted rounded mt-1 max-h-48 overflow-y-auto">
                {JSON.stringify(slice, null, 2)}
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
