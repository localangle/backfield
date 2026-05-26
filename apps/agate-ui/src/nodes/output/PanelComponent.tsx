// Auto-injected metadata for Output
const nodeMetadata = {
  "type": "Output",
  "label": "JSON Output",
  "icon": "Braces",
  "color": "bg-slate-500",
  "description": "Consolidate results from multiple nodes",
  "category": "output",
  "requiredUpstreamNodes": [],
  "dependencyHelperText": "Consolidates results from multiple nodes into a single JSON object.",
  "inputs": [
    {
      "id": "data",
      "label": "Any Data",
      "type": "any",
      "required": true
    }
  ],
  "outputs": [
    {
      "id": "consolidated",
      "label": "Consolidated",
      "type": "object"
    }
  ],
  "defaultParams": {
    "exclude": null,
    "include": null
  }
};

import { NodePanelTabGate } from '@/components/node-panel/NodePanelTabContext'
import {
  NodePanelJsonPreview,
  NodePanelOutputsSection,
} from '@/components/node-panel/NodePanelOutputsSection'
import { getNodeOutputById, type NodeOutputLookupSpec } from '@/lib/nodeOutputs'

interface OutputPanelProps {
  node: any
  currentRun?: any
  nodeOutputLookupSpec?: NodeOutputLookupSpec | null
}

export default function OutputPanel({ node, currentRun, nodeOutputLookupSpec }: OutputPanelProps) {
  const rawOutputs = currentRun?.node_outputs as Record<string, unknown> | undefined
  const slice = rawOutputs
    ? getNodeOutputById(rawOutputs, node.id, nodeOutputLookupSpec ?? undefined)
    : undefined

  return (
    <NodePanelTabGate tab="outputs">
      {slice !== undefined && slice !== null ? (
        <NodePanelOutputsSection title="Consolidated output">
          <NodePanelJsonPreview value={slice} maxHeightClassName="max-h-[min(24rem,50vh)]" />
        </NodePanelOutputsSection>
      ) : null}
    </NodePanelTabGate>
  )
}
