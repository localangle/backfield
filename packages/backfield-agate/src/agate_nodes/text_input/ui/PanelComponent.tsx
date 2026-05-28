import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'

interface TextInputPanelProps {
  node: any
  /** Optional callback fired alongside setNodes — kept so callers can react to edits. */
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
  editMode,
  setNodes,
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
    <>
      <div className="space-y-3">
        <div>
          <Label className="text-sm font-medium">Description</Label>
          <p className="text-sm text-muted-foreground mt-1">
            This node provides text input for processing by downstream nodes. The text is passed
            to connected nodes and changes are saved automatically.
          </p>
        </div>
      </div>

      <div className="pt-4 border-t">
        <div>
          <Label className="text-sm font-medium">Parameters</Label>
        </div>

        <div className="space-y-2 mt-2">
          <div>
            <Label htmlFor="node-text" className="text-xs text-muted-foreground">
              Input Text
            </Label>
            <Textarea
              id="node-text"
              value={node.data.text || ''}
              onChange={(e) => handleChange(e.target.value)}
              placeholder="Enter article text..."
              className="min-h-[300px] mt-1"
              disabled={isDisabled}
            />
          </div>
        </div>
      </div>
    </>
  )
}
