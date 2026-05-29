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
  )
}
