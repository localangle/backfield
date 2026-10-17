import { NodePanelTabGate } from '@/components/node-panel/NodePanelTabContext'
import { FieldLabel } from '@/components/node-panel/FieldLabel'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { getNodeOutputById } from '@backfield/ui/nodeOutputs'
import type { Dispatch, SetStateAction } from 'react'
import type { Node } from 'reactflow'

interface ProcessingGuardPanelProps {
  node: { id: string; data?: Record<string, unknown> }
  editMode?: boolean
  setNodes?: Dispatch<SetStateAction<Node[]>>
  currentRun?: { node_outputs?: Record<string, unknown> | null } | null
}

type GuardCriterion = {
  id: string
  type: 'word_count' | 'estimated_entity_references'
  operator?: 'less_than' | 'greater_than'
  threshold: number | ''
}

type GuardSummary = {
  disposition?: string
  continued_anyway?: boolean
  criteria?: GuardFinding[]
}

type GuardFinding = {
  criterion_id?: string
  type?: string
  observed?: number
  threshold?: number
  estimation?: boolean
  triggered?: boolean
  message?: string
}

function asCriteria(raw: unknown): GuardCriterion[] {
  if (!Array.isArray(raw)) return []
  return raw.filter((entry): entry is GuardCriterion => {
    if (!entry || typeof entry !== 'object') return false
    const row = entry as GuardCriterion
    return row.type === 'word_count' || row.type === 'estimated_entity_references'
  })
}

const DEFAULT_ENTITY_LIMIT = 50

function newId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `criterion-${Date.now()}`
}

export default function ProcessingGuardPanel({
  node,
  editMode = false,
  setNodes,
  currentRun,
}: ProcessingGuardPanelProps) {
  const defaults = (nodeMetadata?.defaultParams || {}) as Record<string, unknown>
  const data = { ...defaults, ...(node.data || {}) }
  const criteria = asCriteria(data.criteria)

  const patchCriteria = (next: GuardCriterion[]) => {
    if (!editMode || !setNodes) return
    setNodes((nodes) =>
      nodes.map((entry) =>
        entry.id === node.id ? { ...entry, data: { ...(entry.data || {}), criteria: next } } : entry,
      ),
    )
  }

  const updateCriterion = (id: string, patch: Partial<GuardCriterion>) => {
    patchCriteria(criteria.map((criterion) => (criterion.id === id ? { ...criterion, ...patch } : criterion)))
  }

  const addCriterion = (criterion: GuardCriterion) => {
    if (!editMode || !setNodes) return
    setNodes((nodes) =>
      nodes.map((entry) => {
        if (entry.id !== node.id) return entry
        const current = asCriteria(entry.data?.criteria)
        if (current.some((row) => row.type === criterion.type)) return entry
        return {
          ...entry,
          data: { ...(entry.data || {}), criteria: [...current, criterion] },
        }
      }),
    )
  }

  const hasLengthLimit = criteria.some((criterion) => criterion.type === 'word_count')
  const hasEntityLimit = criteria.some((criterion) => criterion.type === 'estimated_entity_references')

  const nodeOutput = getNodeOutputById(
    currentRun?.node_outputs as Record<string, unknown> | undefined,
    node.id,
  )
  const summary =
    nodeOutput && typeof nodeOutput === 'object'
      ? ((nodeOutput as Record<string, unknown>).processing_guard as Record<string, unknown> | undefined)
      : undefined
  const guardSummary = summary as GuardSummary | undefined
  const findings = Array.isArray(guardSummary?.criteria) ? guardSummary.criteria : []
  const continuedAnyway = guardSummary?.continued_anyway === true

  return (
    <>
      <NodePanelTabGate tab="settings">
        <div className="space-y-4">
          {criteria.length === 0 ? (
            <p className="text-sm text-muted-foreground">No limits yet. Every story continues.</p>
          ) : (
            <div className="space-y-3">
              {criteria.map((criterion) => (
                <div key={criterion.id} className="space-y-2 rounded-md border p-3">
                  <div className="flex items-center justify-between gap-2">
                    <Label className="text-sm">
                      {criterion.type === 'word_count' ? 'Story length' : 'Entities'}
                    </Label>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      disabled={!editMode}
                      onClick={() => patchCriteria(criteria.filter((entry) => entry.id !== criterion.id))}
                    >
                      Remove
                    </Button>
                  </div>
                  {criterion.type === 'word_count' ? (
                    <div className="space-y-2">
                      <FieldLabel htmlFor={`guard-op-${criterion.id}`}>When the story is</FieldLabel>
                      <select
                        id={`guard-op-${criterion.id}`}
                        className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm"
                        disabled={!editMode}
                        value={criterion.operator === 'less_than' ? 'less_than' : 'greater_than'}
                        onChange={(event) =>
                          updateCriterion(criterion.id, {
                            operator: event.target.value === 'less_than' ? 'less_than' : 'greater_than',
                          })
                        }
                      >
                        <option value="greater_than">Longer than</option>
                        <option value="less_than">Shorter than</option>
                      </select>
                    </div>
                  ) : (
                    <p className="text-xs text-muted-foreground">
                      Estimates the number of distinct entities (people, places, organizations) in a story.
                    </p>
                  )}
                  <div className="space-y-2">
                    <FieldLabel htmlFor={`guard-threshold-${criterion.id}`} required>
                      {criterion.type === 'word_count' ? 'Words' : 'Entity limit'}
                    </FieldLabel>
                    <Input
                      id={`guard-threshold-${criterion.id}`}
                      value={criterion.threshold === '' ? '' : String(criterion.threshold)}
                      disabled={!editMode}
                      onChange={(event) => {
                        const next = event.target.value.replace(/[^\d]/g, '')
                        updateCriterion(criterion.id, { threshold: next === '' ? '' : Number(next) })
                      }}
                    />
                  </div>
                </div>
              ))}
            </div>
          )}
          {hasLengthLimit && hasEntityLimit ? null : (
            <div className="flex flex-wrap gap-2">
              {hasLengthLimit ? null : (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={!editMode}
                  onClick={() =>
                    addCriterion({
                      id: newId(),
                      type: 'word_count',
                      operator: 'greater_than',
                      threshold: 5000,
                    })
                  }
                >
                  Add length limit
                </Button>
              )}
              {hasEntityLimit ? null : (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={!editMode}
                  onClick={() =>
                    addCriterion({
                      id: newId(),
                      type: 'estimated_entity_references',
                      threshold: DEFAULT_ENTITY_LIMIT,
                    })
                  }
                >
                  Add entity limit
                </Button>
              )}
            </div>
          )}
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
              <Label className="text-xs font-medium text-muted-foreground">Result</Label>
              <p className="text-sm mt-1">
                {continuedAnyway
                  ? 'Limits were exceeded. This story was processed anyway.'
                  : summary.disposition === 'needs_attention'
                    ? 'Needs attention. Later steps did not run.'
                    : 'Within the limits. Later steps can run.'}
              </p>
            </div>
            <div className="space-y-2">
              {findings.length === 0 ? (
                <p className="text-sm text-muted-foreground">No limits were checked.</p>
              ) : (
                findings.map((finding) => (
                  <div key={finding.criterion_id} className="rounded-md border p-3 space-y-1">
                    <p className="text-sm">{finding.message}</p>
                    <p className="text-xs text-muted-foreground">
                      {finding.estimation ? 'Estimated' : 'Counted'} {String(finding.observed ?? '—')}
                      {finding.threshold != null ? ` (limit ${finding.threshold})` : ''}
                    </p>
                  </div>
                ))
              )}
            </div>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">Run the flow to see whether a story was paused.</p>
        )}
      </NodePanelTabGate>
    </>
  )
}
