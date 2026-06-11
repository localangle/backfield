// Auto-injected metadata for CustomExtract
const nodeMetadata = {
  "type": "CustomExtract",
  "name": "CustomExtract",
  "label": "Custom Extract",
  "description": "Extract records you define — like ingredients, artists, or event details — with supporting passages from the text.",
  "category": "extraction",
  "icon": "Table",
  "color": "bg-amber-500",
  "requiredProjectModelCapabilities": [
    "generative"
  ],
  "requiredUpstreamNodes": [],
  "dependencyHelperText": "Requires upstream text, such as from Text Input or JSON Input.",
  "inputs": [
    {
      "id": "text",
      "label": "Text",
      "type": "string",
      "required": true
    }
  ],
  "outputs": [
    {
      "id": "text",
      "label": "Text",
      "type": "string"
    },
    {
      "id": "custom_records",
      "label": "Custom records",
      "type": "object"
    }
  ],
  "defaultParams": {
    "model": "",
    "aiModelConfigId": null,
    "record_type": "",
    "label": "",
    "fields": [],
    "instructions": "",
    "llmTimeout": 600
  }
};

import { useEffect, useMemo, useState } from 'react'
import { NodePanelTabGate } from '@/components/node-panel/NodePanelTabContext'
import type { GraphPanelContext, ProjectAiModelOption } from '@/components/NodePanel'
import { getNodeOutputById, type NodeOutputLookupSpec } from '@/lib/nodeOutputs'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ArrowDown, ArrowUp, Plus, Trash2 } from 'lucide-react'
import { buildExampleCustomRecordsOutput } from './exampleOutput'
import {
  INVALID_AI_MODEL_SELECTION_VALUE as INVALID_SELECTION_VALUE,
  catalogToSelectOptions,
  hasExplicitAiModelChoice,
  resolvedAiModelSelectValue,
} from '@/lib/nodePanelAiModel'

const FIELD_TYPE_OPTIONS = [
  { id: 'string', label: 'Text' },
  { id: 'number', label: 'Number' },
  { id: 'boolean', label: 'Yes / no' },
  { id: 'date', label: 'Date' },
  { id: 'string_list', label: 'List of text' },
] as const

type FieldTypeId = (typeof FIELD_TYPE_OPTIONS)[number]['id']

export type CustomExtractField = {
  name: string
  label: string
  type: FieldTypeId
  description: string
}

const MODEL_KEYS = {
  configIdKey: 'aiModelConfigId',
  modelKey: 'model',
} as const

/** Keep record/field identifiers lowercase with underscores; strip disallowed characters. */
function sanitizeSlugInput(raw: string): string {
  return raw
    .toLowerCase()
    .replace(/[\s-]+/g, '_')
    .replace(/[^a-z0-9_]/g, '')
    .replace(/_+/g, '_')
    .replace(/^[_0-9]+/, '')
}

function normalizeFieldType(raw: unknown): FieldTypeId {
  const value = typeof raw === 'string' ? raw.trim().toLowerCase() : 'string'
  const match = FIELD_TYPE_OPTIONS.find((option) => option.id === value)
  return match?.id ?? 'string'
}

export function normalizeFields(raw: unknown): CustomExtractField[] {
  if (!Array.isArray(raw)) return []
  const fields: CustomExtractField[] = []
  for (const entry of raw) {
    if (entry === null || typeof entry !== 'object' || Array.isArray(entry)) continue
    const record = entry as Record<string, unknown>
    fields.push({
      name: typeof record.name === 'string' ? record.name : '',
      label: typeof record.label === 'string' ? record.label : '',
      type: normalizeFieldType(record.type),
      description: typeof record.description === 'string' ? record.description : '',
    })
  }
  return fields
}

function fieldTypeLabel(type: string): string {
  return FIELD_TYPE_OPTIONS.find((option) => option.id === type)?.label ?? 'Text'
}

function duplicateFieldNames(fields: CustomExtractField[]): string[] {
  const seen = new Set<string>()
  const duplicates = new Set<string>()
  for (const field of fields) {
    if (!field.name) continue
    if (seen.has(field.name)) duplicates.add(field.name)
    seen.add(field.name)
  }
  return [...duplicates]
}

type RecordSetOutput = {
  label?: string
  schema?: Array<{ name?: string; label?: string; type?: string }>
  records?: Array<{
    fields?: Record<string, unknown>
    mentions?: Array<{ text?: string }>
    confidence?: number
  }>
  dropped_ungrounded?: number
}

function recordSetsFromOutput(nodeOutput: unknown): Array<[string, RecordSetOutput]> {
  if (nodeOutput === null || typeof nodeOutput !== 'object') return []
  const block = (nodeOutput as { custom_records?: unknown }).custom_records
  if (block === null || typeof block !== 'object' || Array.isArray(block)) return []
  return Object.entries(block as Record<string, unknown>).filter(
    (entry): entry is [string, RecordSetOutput] =>
      entry[1] !== null && typeof entry[1] === 'object' && !Array.isArray(entry[1]),
  )
}

function cellDisplayValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  if (Array.isArray(value)) return value.map((item) => String(item)).join(', ')
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  return String(value)
}

const OUTPUT_PREVIEW_ROW_LIMIT = 8

interface CustomExtractPanelProps {
  node: { id: string; data?: Record<string, unknown> }
  currentRun?: { node_outputs?: Record<string, unknown> }
  editMode?: boolean
  setNodes?: (nodes: unknown) => void
  graphContext?: GraphPanelContext
  nodeOutputLookupSpec?: NodeOutputLookupSpec | null
}

export default function CustomExtractPanel({
  node,
  editMode,
  setNodes,
  currentRun,
  graphContext,
  nodeOutputLookupSpec,
}: CustomExtractPanelProps) {
  const paramsRecord = {
    ...(nodeMetadata.defaultParams || {}),
    ...(node.data || {}),
  } as Record<string, unknown>

  const projectId = graphContext?.projectId ?? null
  const [catalogRows, setCatalogRows] = useState<ProjectAiModelOption[]>([])
  const [catalogLoading, setCatalogLoading] = useState(false)
  const [catalogError, setCatalogError] = useState<string | null>(null)

  useEffect(() => {
    const fetcher = graphContext?.fetchProjectAiModels
    if (projectId == null || fetcher == null) {
      setCatalogRows([])
      setCatalogError(null)
      setCatalogLoading(false)
      return
    }
    let cancelled = false
    setCatalogLoading(true)
    setCatalogError(null)
    void fetcher(['text', 'json'])
      .then((rows) => {
        if (!cancelled) {
          setCatalogRows(rows)
          setCatalogLoading(false)
        }
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setCatalogRows([])
          setCatalogError(e instanceof Error ? e.message : 'Could not load models.')
          setCatalogLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [projectId, graphContext?.fetchProjectAiModels])

  const modelSelectOptions = useMemo(() => catalogToSelectOptions(catalogRows), [catalogRows])
  const resolvedUnderlying = resolvedAiModelSelectValue(paramsRecord, catalogRows, MODEL_KEYS)
  const selectionValid =
    resolvedUnderlying !== '' && modelSelectOptions.some((o) => o.selectValue === resolvedUnderlying)

  const showInvalidPersisted =
    Boolean(editMode && setNodes && projectId != null && catalogRows.length > 0 && !catalogLoading) &&
    hasExplicitAiModelChoice((node.data || {}) as Record<string, unknown>, MODEL_KEYS) &&
    !selectionValid

  const radixSelectValue = selectionValid
    ? resolvedUnderlying
    : showInvalidPersisted
      ? INVALID_SELECTION_VALUE
      : undefined

  useEffect(() => {
    if (!editMode || !setNodes || catalogLoading || catalogRows.length === 0) return
    const data = (node.data || {}) as Record<string, unknown>
    if (hasExplicitAiModelChoice(data, MODEL_KEYS)) return
    const first = modelSelectOptions[0]
    if (!first) return
    setNodes((nds: { id: string; data?: Record<string, unknown> }[]) =>
      nds.map((n) =>
        n.id === node.id
          ? {
              ...n,
              data: {
                ...(n.data || {}),
                model: first.providerModelId,
                aiModelConfigId: first.configId ?? null,
              },
            }
          : n,
      ),
    )
  }, [
    editMode,
    setNodes,
    catalogLoading,
    catalogRows,
    modelSelectOptions,
    node.id,
    node.data,
  ])

  const isDisabled = !(editMode && setNodes)
  const currentRecordType =
    typeof paramsRecord.record_type === 'string' ? paramsRecord.record_type : ''
  const currentLabel = typeof paramsRecord.label === 'string' ? paramsRecord.label : ''
  const currentInstructions =
    typeof paramsRecord.instructions === 'string' ? paramsRecord.instructions : ''
  const fields = useMemo(() => normalizeFields(paramsRecord.fields), [paramsRecord.fields])
  const duplicateNames = duplicateFieldNames(fields)

  const patchNodeData = (updates: Record<string, unknown>) => {
    if (!setNodes) return
    setNodes((nds: { id: string; data?: Record<string, unknown> }[]) =>
      nds.map((n) =>
        n.id === node.id ? { ...n, data: { ...(n.data || {}), ...updates } } : n,
      ),
    )
  }

  const handleModelChange = (selectValue: string) => {
    if (!setNodes || selectValue === INVALID_SELECTION_VALUE) return
    const row = modelSelectOptions.find((o) => o.selectValue === selectValue)
    patchNodeData({
      model: row?.providerModelId ?? selectValue,
      aiModelConfigId: row?.configId ?? null,
    })
  }

  const setFields = (next: CustomExtractField[]) => {
    patchNodeData({ fields: next })
  }

  const updateField = (index: number, updates: Partial<CustomExtractField>) => {
    setFields(fields.map((field, i) => (i === index ? { ...field, ...updates } : field)))
  }

  const addField = () => {
    setFields([...fields, { name: '', label: '', type: 'string', description: '' }])
  }

  const removeField = (index: number) => {
    setFields(fields.filter((_, i) => i !== index))
  }

  const moveField = (index: number, direction: -1 | 1) => {
    const target = index + direction
    if (target < 0 || target >= fields.length) return
    const next = [...fields]
    const [moved] = next.splice(index, 1)
    next.splice(target, 0, moved)
    setFields(next)
  }

  const displayModelLabel =
    modelSelectOptions.find((o) => o.selectValue === resolvedUnderlying)?.label ??
    (showInvalidPersisted
      ? 'Previous model unavailable'
      : resolvedUnderlying !== ''
        ? String(paramsRecord.model ?? resolvedUnderlying)
        : '—')

  const nodeOutput = getNodeOutputById(
    currentRun?.node_outputs as Record<string, unknown> | undefined,
    node.id,
    nodeOutputLookupSpec ?? undefined,
  )
  const recordSets = recordSetsFromOutput(nodeOutput)
  const exampleOutputPreview = useMemo(
    () =>
      buildExampleCustomRecordsOutput({
        recordType: currentRecordType,
        label: currentLabel,
        fields,
      }),
    [currentLabel, currentRecordType, fields],
  )

  return (
    <>
      <NodePanelTabGate tab="info">
        <div className="space-y-2">
          <Label className="text-sm font-medium">How this step works</Label>
          <p className="text-sm text-muted-foreground mt-1">
            This step reads the story text and pulls out records you define — like ingredients
            from a recipe or artists from arts coverage. Each record keeps the passage from the
            story that supports it, so reviewers can always check the source.
          </p>
          {nodeMetadata.dependencyHelperText ? (
            <p className="text-sm text-muted-foreground mt-3">{nodeMetadata.dependencyHelperText}</p>
          ) : null}
        </div>
      </NodePanelTabGate>

      <NodePanelTabGate tab="settings">
        <div className="space-y-4">
          <div>
            <Label className="text-sm font-medium">Record set name</Label>
            {editMode && setNodes ? (
              <Input
                value={currentLabel}
                onChange={(e) => {
                  const nextLabel = e.target.value
                  const updates: Record<string, unknown> = { label: nextLabel }
                  if (!currentRecordType.trim()) {
                    updates.record_type = sanitizeSlugInput(nextLabel)
                  }
                  patchNodeData(updates)
                }}
                placeholder="Ingredients"
                className="mt-2 h-8 text-xs"
              />
            ) : (
              <div className="flex justify-between items-center p-2 bg-muted rounded mt-2">
                <span className="text-muted-foreground">Record set name</span>
                <span className="font-medium text-xs">{currentLabel.trim() || '—'}</span>
              </div>
            )}
            <p className="text-xs text-muted-foreground mt-1">
              Shown as the table title when reviewing results.
            </p>
          </div>

          <div>
            <Label className="text-sm font-medium">Record type</Label>
            {editMode && setNodes ? (
              <Input
                value={currentRecordType}
                onChange={(e) => {
                  patchNodeData({ record_type: sanitizeSlugInput(e.target.value) })
                }}
                placeholder="ingredients"
                className="mt-2 h-8 text-xs font-mono"
                spellCheck={false}
                autoCapitalize="off"
                autoCorrect="off"
              />
            ) : (
              <div className="flex justify-between items-center p-2 bg-muted rounded mt-2">
                <span className="text-muted-foreground">Record type</span>
                <span className="font-medium text-xs font-mono">
                  {currentRecordType.trim() || '—'}
                </span>
              </div>
            )}
            <p className="text-xs text-muted-foreground mt-1">
              A short id that keeps these records together across runs. Letters, numbers, and
              underscores only — spaces become underscores as you type.
            </p>
          </div>

          <div>
            <Label className="text-sm font-medium">Fields</Label>
            <p className="text-xs text-muted-foreground mt-1">
              Each record gets these fields, like columns in a table.
            </p>
            <div className="mt-2 space-y-3">
              {fields.length === 0 ? (
                <p className="text-xs text-muted-foreground p-2 bg-muted rounded">
                  No fields yet. Add at least one field to describe what each record contains.
                </p>
              ) : null}
              {fields.map((field, index) => (
                <div key={`field-${index}`} className="border rounded-md p-2 space-y-2">
                  <div className="flex items-center gap-2">
                    <Input
                      value={field.label}
                      onChange={(e) => {
                        const nextLabel = e.target.value
                        updateField(index, {
                          label: nextLabel,
                          name: sanitizeSlugInput(nextLabel),
                        })
                      }}
                      placeholder="Field name (for example Quantity)"
                      className="h-8 text-xs flex-1"
                      disabled={isDisabled}
                    />
                    <Select
                      value={field.type}
                      onValueChange={(value) => {
                        updateField(index, { type: normalizeFieldType(value) })
                      }}
                      disabled={isDisabled}
                    >
                      <SelectTrigger className="h-8 text-xs w-[110px]">
                        <SelectValue placeholder="Type" />
                      </SelectTrigger>
                      <SelectContent>
                        {FIELD_TYPE_OPTIONS.map((option) => (
                          <SelectItem key={option.id} value={option.id}>
                            {option.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    {editMode && setNodes ? (
                      <div className="flex items-center gap-1">
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7"
                          onClick={() => moveField(index, -1)}
                          disabled={index === 0}
                          aria-label="Move field up"
                        >
                          <ArrowUp className="h-3 w-3" />
                        </Button>
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7"
                          onClick={() => moveField(index, 1)}
                          disabled={index === fields.length - 1}
                          aria-label="Move field down"
                        >
                          <ArrowDown className="h-3 w-3" />
                        </Button>
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7 text-destructive"
                          onClick={() => removeField(index)}
                          aria-label="Remove field"
                        >
                          <Trash2 className="h-3 w-3" />
                        </Button>
                      </div>
                    ) : null}
                  </div>
                  <Input
                    value={field.description}
                    onChange={(e) => {
                      updateField(index, { description: e.target.value })
                    }}
                    placeholder="Optional: what should go in this field?"
                    className="h-8 text-xs"
                    disabled={isDisabled}
                  />
                </div>
              ))}
            </div>
            {duplicateNames.length > 0 ? (
              <p className="text-xs text-destructive mt-2">
                Two fields ended up with the same name ({duplicateNames.join(', ')}). Rename one of
                them so each field is unique.
              </p>
            ) : null}
            {editMode && setNodes ? (
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="mt-2 h-8 text-xs"
                onClick={addField}
              >
                <Plus className="h-3 w-3 mr-1" /> Add field
              </Button>
            ) : null}
          </div>

          <div>
            <Label className="text-sm font-medium">Extraction model</Label>
            {editMode && setNodes ? (
              <>
                {(projectId == null || graphContext?.fetchProjectAiModels == null) && (
                  <p className="text-xs text-muted-foreground mt-2">
                    Save this flow under a project to choose models your organization enabled for
                    this project.
                  </p>
                )}
                {projectId != null && catalogLoading && (
                  <p className="text-xs text-muted-foreground mt-2">Loading models…</p>
                )}
                {catalogError != null && catalogError !== '' ? (
                  <p className="text-xs text-destructive mt-2">{catalogError}</p>
                ) : null}
                {!catalogLoading &&
                  !catalogError &&
                  projectId != null &&
                  graphContext?.fetchProjectAiModels != null &&
                  modelSelectOptions.length === 0 && (
                    <p className="text-xs text-muted-foreground mt-2">
                      No models available for this project yet. Ask an administrator to enable
                      models for your organization, then turn them on for this project in project
                      settings if needed.
                    </p>
                  )}
                {showInvalidPersisted && (
                  <p className="text-xs text-muted-foreground mt-2">
                    The saved model is no longer available. Choose another model below.
                  </p>
                )}
                <Select
                  value={radixSelectValue}
                  onValueChange={handleModelChange}
                  disabled={isDisabled || modelSelectOptions.length === 0}
                >
                  <SelectTrigger className="h-8 text-xs mt-2">
                    <SelectValue placeholder="Choose a model" />
                  </SelectTrigger>
                  <SelectContent>
                    {showInvalidPersisted ? (
                      <SelectItem disabled value={INVALID_SELECTION_VALUE}>
                        Saved model unavailable
                      </SelectItem>
                    ) : null}
                    {modelSelectOptions.map((m) => (
                      <SelectItem key={`ce-${m.selectValue}`} value={m.selectValue}>
                        {m.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground mt-1">
                  Set available models in your organization settings.
                </p>
              </>
            ) : (
              <>
                <div className="flex justify-between items-center p-2 bg-muted rounded mt-2">
                  <span className="text-muted-foreground">Extraction model</span>
                  <span className="font-medium text-xs">{displayModelLabel}</span>
                </div>
                <p className="text-xs text-muted-foreground mt-1">
                  Set available models in your organization settings.
                </p>
              </>
            )}
          </div>
        </div>
      </NodePanelTabGate>

      <NodePanelTabGate tab="prompts">
        <div>
          <Label className="text-sm font-medium">Extraction instructions</Label>
          {editMode && setNodes ? (
            <Textarea
              value={currentInstructions}
              onChange={(e) => {
                patchNodeData({ instructions: e.target.value })
              }}
              placeholder="For example: Only pull ingredients from the recipe card, not the narrative."
              className="mt-2 min-h-[160px] px-3 py-2 text-xs border border-input bg-background rounded-md focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
            />
          ) : (
            <div className="mt-2 p-2 bg-muted rounded max-h-48 overflow-y-auto">
              <pre className="text-xs whitespace-pre-wrap">
                {currentInstructions || 'No extra instructions.'}
              </pre>
            </div>
          )}
          <p className="text-xs text-muted-foreground mt-1">
            Optional guidance for what to include or skip. The fields you defined on the Settings
            tab decide what each record contains.
          </p>
        </div>
      </NodePanelTabGate>

      <NodePanelTabGate tab="outputs">
        <div className="space-y-4">
          <div>
            <Label className="text-sm font-medium">Example output</Label>
            <p className="text-xs text-muted-foreground mt-1">
              Based on the fields you set up in Settings. Run the flow to see real records from
              your story.
            </p>
            {exampleOutputPreview === null ? (
              <p className="text-xs text-muted-foreground mt-2 p-2 bg-muted rounded">
                Add at least one field on the Settings tab to see a preview here.
              </p>
            ) : (
              <pre className="mt-2 max-h-64 overflow-y-auto rounded-md border bg-muted/50 p-3 text-xs font-mono whitespace-pre-wrap break-words">
                {JSON.stringify(exampleOutputPreview, null, 2)}
              </pre>
            )}
          </div>

          {recordSets.length > 0 ? (
            <div className="border-t pt-4 space-y-4">
              <Label className="text-sm font-medium">Latest run</Label>
              {recordSets.map(([recordType, recordSet]) => {
              const schema = Array.isArray(recordSet.schema) ? recordSet.schema : []
              const records = Array.isArray(recordSet.records) ? recordSet.records : []
              const dropped =
                typeof recordSet.dropped_ungrounded === 'number'
                  ? recordSet.dropped_ungrounded
                  : 0
              return (
                <div key={recordType}>
                  <Label className="text-sm font-medium">
                    {recordSet.label || recordType.replace(/_/g, ' ')}
                  </Label>
                  {records.length === 0 ? (
                    <p className="text-xs text-muted-foreground mt-2">
                      No records found in the latest run.
                    </p>
                  ) : (
                    <div className="mt-2 border rounded overflow-x-auto">
                      <table className="w-full text-xs">
                        <thead>
                          <tr className="bg-muted text-left">
                            {schema.map((column, columnIndex) => (
                              <th key={`${recordType}-h-${columnIndex}`} className="px-2 py-1 font-medium">
                                {column.label || column.name || ''}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {records.slice(0, OUTPUT_PREVIEW_ROW_LIMIT).map((record, rowIndex) => (
                            <tr key={`${recordType}-r-${rowIndex}`} className="border-t">
                              {schema.map((column, columnIndex) => (
                                <td key={`${recordType}-c-${rowIndex}-${columnIndex}`} className="px-2 py-1">
                                  {cellDisplayValue(
                                    column.name ? record.fields?.[column.name] : undefined,
                                  )}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                  {records.length > OUTPUT_PREVIEW_ROW_LIMIT ? (
                    <p className="text-xs text-muted-foreground mt-1">
                      Showing the first {OUTPUT_PREVIEW_ROW_LIMIT} of {records.length} records.
                    </p>
                  ) : null}
                  {dropped > 0 ? (
                    <p className="text-xs text-muted-foreground mt-1">
                      {dropped} suggested record{dropped === 1 ? ' was' : 's were'} left out because
                      no supporting passage was found in the story.
                    </p>
                  ) : null}
                </div>
              )
            })}
            </div>
          ) : null}
        </div>
      </NodePanelTabGate>
    </>
  )
}
