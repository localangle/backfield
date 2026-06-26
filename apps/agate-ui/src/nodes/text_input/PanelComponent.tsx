// Auto-injected metadata for TextInput
const nodeMetadata = {
  "type": "TextInput",
  "label": "Text Input",
  "icon": "FileText",
  "color": "bg-blue-500",
  "description": "Type or paste text to be processed by this flow.",
  "category": "input",
  "inputs": [],
  "outputs": [
    {
      "id": "text",
      "label": "Text",
      "type": "string"
    }
  ],
  "defaultParams": {
    "text": ""
  }
};

import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import IngressApiRunsSection from '@/components/node-panel/IngressApiRunsSection'
import type { GraphPanelContext } from '@/components/NodePanel'

interface TextInputPanelProps {
  node: any
  /** Optional callback fired alongside setNodes — kept so callers can react to edits. */
  onChange?: (text: string) => void
  editMode?: boolean
  setNodes?: (nodes: any) => void
  graphContext?: GraphPanelContext
}

export default function TextInputPanel({
  node,
  onChange,
  editMode,
  setNodes,
  graphContext,
}: TextInputPanelProps) {
  const isDisabled = !(editMode && setNodes)

  const handleChange = (text: string) => {
    if (setNodes) {
      setNodes((nds: any[]) =>
        nds.map((n: any) => (n.id === node.id ? { ...n, data: { ...n.data, text } } : n)),
      )
    }
    onChange?.(text)
  }

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="node-text">Input text</Label>
        <Textarea
          id="node-text"
          value={node.data.text || ''}
          onChange={(e) => handleChange(e.target.value)}
          placeholder="Enter article text..."
          className="min-h-[300px] mt-1"
          disabled={isDisabled}
        />
      </div>

      <IngressApiRunsSection
        node={node}
        editMode={editMode}
        setNodes={setNodes}
        publicRunEnabled={Boolean(graphContext?.publicRunEnabled)}
        onPublicRunEnabledChange={graphContext?.onPublicRunEnabledChange}
      />
    </div>
  )
}
