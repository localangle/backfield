import { NodePanelTabGate } from '@/components/node-panel/NodePanelTabContext'
import { Label } from '@/components/ui/label'
import { getNodeOutputById } from '@backfield/ui/nodeOutputs'

interface GatherPanelProps {
  node: { id: string; data?: Record<string, unknown> }
  currentRun?: { node_outputs?: Record<string, unknown> }
}

export default function GatherPanel({ node, currentRun }: GatherPanelProps) {
  const nodeOutput = getNodeOutputById(
    currentRun?.node_outputs as Record<string, unknown> | undefined,
    node.id,
  )
  const gatheredKeys =
    nodeOutput && typeof nodeOutput === 'object' && nodeOutput !== null
      ? Object.keys(nodeOutput as Record<string, unknown>)
      : []

  return (
    <>
      <NodePanelTabGate tab="settings">
        <div className="space-y-3">
          <div>
            <Label className="text-sm font-medium">How it works</Label>
            <p className="text-sm text-muted-foreground mt-1 leading-relaxed">
              Gather waits until the other nodes in this flow have finished, then combines their
              outputs into one collection you can pass to the next step.
            </p>
          </div>
          <p className="text-sm text-muted-foreground p-3 bg-muted rounded">
            No settings required. Connect downstream nodes after Gather to use the combined output.
          </p>
        </div>
      </NodePanelTabGate>

      <NodePanelTabGate tab="info">
        {nodeMetadata.dependencyHelperText ? (
          <p className="text-sm text-muted-foreground leading-relaxed">
            {nodeMetadata.dependencyHelperText}
          </p>
        ) : null}
      </NodePanelTabGate>

      <NodePanelTabGate tab="outputs">
        {nodeOutput ? (
          <div className="space-y-3">
            <div>
              <Label className="text-xs font-medium text-muted-foreground">Included outputs</Label>
              <p className="text-xs font-mono p-2 bg-muted rounded mt-1 break-words">
                {gatheredKeys.length > 0 ? gatheredKeys.join(', ') : '—'}
              </p>
            </div>
            <div>
              <Label className="text-xs font-medium text-muted-foreground">Preview</Label>
              <pre className="text-xs font-mono p-2 bg-muted rounded mt-1 max-h-48 overflow-y-auto whitespace-pre-wrap break-words">
                {JSON.stringify(nodeOutput, null, 2).slice(0, 1200)}
                {JSON.stringify(nodeOutput, null, 2).length > 1200 ? '\n…' : ''}
              </pre>
            </div>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">Run the flow to preview gathered output.</p>
        )}
      </NodePanelTabGate>
    </>
  )
}
