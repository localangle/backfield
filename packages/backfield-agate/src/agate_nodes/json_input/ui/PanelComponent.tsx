import { useEffect, useState } from 'react'
import { NodePanelTabGate } from '@/components/node-panel/NodePanelTabContext'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import {
  jsonInputInvalidNodeData,
  parseJsonInputEditorText,
} from '@/lib/jsonInputValidation'
import { getNodeOutputById, type NodeOutputLookupSpec } from '@/lib/nodeOutputs'
import { JSON_INPUT_SCHEMA_EXAMPLE } from './schemaExample'

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

    const result = parseJsonInputEditorText(value)
    if (!result.ok) {
      setJsonError(result.error)
      if (setNodes) {
        setNodes((nds: any[]) =>
          nds.map((n: any) => (n.id === node.id ? { ...n, data: jsonInputInvalidNodeData() } : n)),
        )
      }
      return
    }

    setJsonError('')

    if (setNodes) {
      setNodes((nds: any[]) =>
        nds.map((n: any) => (n.id === node.id ? { ...n, data: result.data } : n)),
      )
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
      <NodePanelTabGate tab="settings">
        <div className="space-y-2">
          <Label htmlFor="node-json">JSON data (must include &quot;text&quot;)</Label>
          <Textarea
            id="node-json"
            value={jsonText}
            onChange={(e) => handleJsonChange(e.target.value)}
            placeholder={`{\n  "text": "Your text here...",\n  "headline": "Optional headline"\n}`}
            className="min-h-[300px] mt-1 font-mono text-xs"
            disabled={isDisabled}
          />
          {jsonError && <p className="text-xs text-red-500 mt-1">{jsonError}</p>}
        </div>
      </NodePanelTabGate>

      <NodePanelTabGate tab="info">
        <div className="space-y-2">
          <p className="text-sm text-muted-foreground leading-relaxed">
            Use a single JSON object. Include a <span className="font-mono">text</span> field (it may
            be empty); other top-level fields are optional and can be referenced in prompts (for
            example{' '}
            <span className="font-mono">{'{headline}'}</span>).
          </p>
          <Label htmlFor="node-json-schema">Example shape</Label>
          <Textarea
            id="node-json-schema"
            readOnly
            value={JSON_INPUT_SCHEMA_EXAMPLE}
            className="min-h-[300px] mt-1 font-mono text-xs bg-muted/40 cursor-default"
            tabIndex={-1}
            aria-readonly
          />
        </div>
      </NodePanelTabGate>

      <NodePanelTabGate tab="outputs">
        {slice && typeof slice.text === 'string' ? (
          <div className="space-y-2">
            <div className="text-xs text-muted-foreground">
              Fields in output: {Object.keys(slice).length}
            </div>
            <div>
              <Label>Output preview</Label>
              <div className="text-xs font-mono p-2 bg-muted rounded mt-1 max-h-48 overflow-y-auto">
                {JSON.stringify(slice, null, 2)}
              </div>
            </div>
          </div>
        ) : null}
      </NodePanelTabGate>
    </>
  )
}
