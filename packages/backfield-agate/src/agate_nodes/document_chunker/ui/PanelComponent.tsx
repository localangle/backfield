import { NodePanelTabGate } from '@/components/node-panel/NodePanelTabContext'
import { FieldLabel } from '@/components/node-panel/FieldLabel'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { getNodeOutputById } from '@backfield/ui/nodeOutputs'
import type { Dispatch, SetStateAction } from 'react'
import type { Node } from 'reactflow'

interface DocumentChunkerPanelProps {
  node: { id: string; data?: Record<string, unknown> }
  editMode?: boolean
  setNodes?: Dispatch<SetStateAction<Node[]>>
  currentRun?: { node_outputs?: Record<string, unknown> | null } | null
}

type ChunkPreview = {
  index?: number
  approximate_tokens?: number
  preview?: string
}

function asPositiveInt(raw: unknown, fallback: number): number {
  if (typeof raw === 'number' && Number.isFinite(raw)) return Math.trunc(raw)
  if (typeof raw === 'string' && raw.trim() !== '' && !Number.isNaN(Number(raw))) {
    return Math.trunc(Number(raw))
  }
  return fallback
}

export default function DocumentChunkerPanel({
  node,
  editMode = false,
  setNodes,
  currentRun,
}: DocumentChunkerPanelProps) {
  const defaults = (nodeMetadata?.defaultParams || {}) as Record<string, unknown>
  const data = { ...defaults, ...(node.data || {}) }
  const targetTokens = asPositiveInt(data.target_tokens, 4000)
  const overlapTokens = asPositiveInt(data.overlap_tokens, 250)

  const patch = (patchData: Record<string, unknown>) => {
    if (!editMode || !setNodes) return
    setNodes((nodes) =>
      nodes.map((entry) =>
        entry.id === node.id
          ? { ...entry, data: { ...(entry.data || {}), ...patchData } }
          : entry,
      ),
    )
  }

  const nodeOutput = getNodeOutputById(
    currentRun?.node_outputs as Record<string, unknown> | undefined,
    node.id,
  )
  const summary =
    nodeOutput && typeof nodeOutput === 'object' && nodeOutput !== null
      ? ((nodeOutput as Record<string, unknown>).chunking_summary as
          | Record<string, unknown>
          | undefined)
      : undefined
  const chunkPreviews = Array.isArray(summary?.chunks)
    ? (summary?.chunks as ChunkPreview[]).slice(0, 12)
    : []

  return (
    <>
      <NodePanelTabGate tab="settings">
        <div className="space-y-4">
          <p className="text-sm text-muted-foreground leading-relaxed">
            Use this when a document is too long for extraction on its own. Backfield keeps one
            story for review and combines results from each piece.
          </p>
          <div className="space-y-2">
            <FieldLabel htmlFor="chunk-target-tokens" required>
              Target piece size
            </FieldLabel>
            <Input
              id="chunk-target-tokens"
              value={String(targetTokens)}
              disabled={!editMode}
              onChange={(event) => {
                const next = event.target.value.replace(/[^\d]/g, '')
                patch({ target_tokens: next === '' ? '' : Number(next) })
              }}
            />
            <p className="text-xs text-muted-foreground">
              Approximate tokens per piece. Larger pieces mean fewer model calls.
            </p>
          </div>
          <div className="space-y-2">
            <FieldLabel htmlFor="chunk-overlap-tokens" required>
              Overlap
            </FieldLabel>
            <Input
              id="chunk-overlap-tokens"
              value={String(overlapTokens)}
              disabled={!editMode}
              onChange={(event) => {
                const next = event.target.value.replace(/[^\d]/g, '')
                patch({ overlap_tokens: next === '' ? '' : Number(next) })
              }}
            />
            <p className="text-xs text-muted-foreground">
              Shared text between neighboring pieces so names and places near boundaries are not
              missed. Must be smaller than the target piece size.
            </p>
          </div>
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
        {summary ? (
          <div className="space-y-3">
            <div>
              <Label className="text-xs font-medium text-muted-foreground">Summary</Label>
              <p className="text-sm mt-1">
                {String(summary.chunk_count ?? 0)} piece
                {Number(summary.chunk_count) === 1 ? '' : 's'}
                {summary.split_required ? '' : ' (document did not need splitting)'}
              </p>
              <p className="text-xs text-muted-foreground mt-1">
                About {String(summary.approximate_document_tokens ?? '—')} tokens in the full
                document.
              </p>
            </div>
            <div className="space-y-2">
              <Label className="text-xs font-medium text-muted-foreground">Piece previews</Label>
              {chunkPreviews.length === 0 ? (
                <p className="text-sm text-muted-foreground">No piece previews available.</p>
              ) : (
                chunkPreviews.map((chunk) => (
                  <div key={String(chunk.index)} className="rounded bg-muted p-2 space-y-1">
                    <p className="text-xs font-medium">
                      Piece {(chunk.index ?? 0) + 1}
                      {typeof chunk.approximate_tokens === 'number'
                        ? ` · ~${chunk.approximate_tokens} tokens`
                        : ''}
                    </p>
                    <p className="text-xs text-muted-foreground break-words">
                      {chunk.preview || '—'}
                    </p>
                  </div>
                ))
              )}
            </div>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            Run the flow to preview how this document was split.
          </p>
        )}
      </NodePanelTabGate>
    </>
  )
}
