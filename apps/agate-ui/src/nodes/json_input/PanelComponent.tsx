// Auto-injected metadata for JSONInput
const nodeMetadata = {
  "type": "JSONInput",
  "label": "JSON Input",
  "icon": "Braces",
  "color": "bg-blue-500",
  "description": "Provide structured JSON data with required text field",
  "category": "input",
  "inputs": [],
  "outputs": [
    {
      "id": "text",
      "label": "Text + Data",
      "type": "object"
    }
  ],
  "defaultParams": {
    "text": ""
  }
};

import { useEffect, useState } from 'react'
import { NodePanelTabGate } from '@/components/node-panel/NodePanelTabContext'
import {
  NodePanelJsonPreview,
  NodePanelOutputsSection,
} from '@/components/node-panel/NodePanelOutputsSection'
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
        setNodes((nds: any[]) => nds.map((n: any) => (n.id === node.id ? { ...n, data: parsed } : n)))
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
      <NodePanelTabGate tab="settings">
        <div className="space-y-2">
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
            Use extra fields (for example headline, url) so downstream steps can reference them.
          </p>
        </div>
      </NodePanelTabGate>

      <NodePanelTabGate tab="outputs">
        {slice ? (
          <NodePanelOutputsSection>
            <div className="text-xs text-muted-foreground">
              Fields in output: {Object.keys(slice).length}
            </div>
            <div>
              <Label className="text-xs font-medium">Output preview</Label>
              <div className="mt-1">
                <NodePanelJsonPreview value={slice} />
              </div>
            </div>
          </NodePanelOutputsSection>
        ) : null}
      </NodePanelTabGate>
    </>
  )
}
