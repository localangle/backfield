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

interface TextInputPanelProps {
  node: any
  onChange?: (text: string) => void
  onRun?: () => void
  running?: boolean
  currentRun?: any
  editMode?: boolean
  setNodes?: (nodes: any) => void
}

export default function TextInputPanel({
  node,
  onChange,
  onRun,
  running,
  currentRun,
  editMode,
  setNodes,
}: TextInputPanelProps) {
  const isDisabled = !(editMode && setNodes)

  return (
    <div className="space-y-2">
      <Label htmlFor="node-text" className="text-xs text-muted-foreground">
        Input text
      </Label>
      <Textarea
        id="node-text"
        value={node.data.text || ''}
        onChange={(e) => onChange?.(e.target.value)}
        placeholder="Enter article text..."
        className="min-h-[300px] mt-1"
        disabled={isDisabled}
      />
    </div>
  )
}
