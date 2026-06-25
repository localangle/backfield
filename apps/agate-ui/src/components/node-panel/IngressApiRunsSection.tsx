import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import {
  inferIngressPublicAlias,
  resolveIngressPublicAlias,
} from '@/lib/ingressApiRuns'

interface IngressApiRunsSectionProps {
  node: { id: string; type?: string; data?: Record<string, unknown> }
  editMode?: boolean
  setNodes?: (updater: (nodes: unknown[]) => unknown[]) => void
  publicRunEnabled: boolean
  onPublicRunEnabledChange?: (enabled: boolean) => void
}

export default function IngressApiRunsSection({
  node,
  editMode,
  setNodes,
  publicRunEnabled,
  onPublicRunEnabledChange,
}: IngressApiRunsSectionProps) {
  const nodeType = String(node.type ?? '')
  const nodeData = node.data ?? {}
  const inputKey = resolveIngressPublicAlias(nodeType, nodeData)
  const isDisabled = !(editMode && setNodes && onPublicRunEnabledChange)

  const handleToggle = (checked: boolean) => {
    onPublicRunEnabledChange?.(checked)
    if (!setNodes) return

    setNodes((nds: unknown[]) =>
      (nds as Array<{ id: string; data?: Record<string, unknown> }>).map((n) => {
        if (n.id !== node.id) return n
        const nextData = { ...(n.data ?? {}) }
        if (checked) {
          nextData.public_alias = inferIngressPublicAlias(nodeType, nextData)
        } else {
          delete nextData.public_alias
        }
        return { ...n, data: nextData }
      }),
    )
  }

  return (
    <div className="space-y-3 border-t pt-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <Label htmlFor="enable-api-runs">Enable API runs</Label>
          <p className="text-xs text-muted-foreground mt-0.5">
            Allow this flow to be started from an integration using your project API key.
          </p>
        </div>
        {isDisabled ? (
          <div className="p-2 bg-muted rounded shrink-0">
            <span className="text-xs">{publicRunEnabled ? 'Yes' : 'No'}</span>
          </div>
        ) : (
          <Switch
            id="enable-api-runs"
            checked={publicRunEnabled}
            onCheckedChange={handleToggle}
          />
        )}
      </div>

      {publicRunEnabled ? (
        <p className="text-xs text-muted-foreground">
          Integration input key:{' '}
          <span className="font-mono text-foreground">{inputKey}</span>
        </p>
      ) : null}
    </div>
  )
}
