import { Label } from '@/components/ui/label'

interface DBOutputPanelProps {
  node: any
  onChange?: (text: string) => void
  onRun?: () => void
  running?: boolean
  currentRun?: any
  editMode?: boolean
  setNodes?: (nodes: any) => void
}

export default function DBOutputPanel(_props: DBOutputPanelProps) {
  return (
    <div className="space-y-3">
      <div>
        <Label className="text-sm font-medium">Description</Label>
        <p className="text-sm text-muted-foreground mt-1">Persists results to Stylebook</p>
      </div>
    </div>
  )
}
