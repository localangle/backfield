// Auto-injected metadata for EmbedImages
const nodeMetadata = {
  "type": "EmbedImages",
  "label": "Embed Images",
  "description": "Write a text description for each image from caption and article context, then embed those descriptions for search and analysis.",
  "category": "embedding",
  "icon": "Image",
  "color": "bg-orange-500",
  "requiredUpstreamNodes": [],
  "requiredProjectModelCapabilities": [
    "generative",
    "embedding"
  ],
  "dependencyHelperText": "Requires upstream images, such as from JSON Input with an images field.",
  "inputs": [
    {
      "id": "images",
      "label": "Images",
      "type": "object",
      "required": true
    }
  ],
  "outputs": [
    {
      "id": "image_embeddings",
      "label": "Image embeddings",
      "type": "array"
    }
  ],
  "defaultParams": {
    "prompt": "Write a clear, detailed description of the image using only the caption and article context provided. Do not invent visual details that are not supported by the context.",
    "descriptionModel": "",
    "descriptionAiModelConfigId": null,
    "embeddingModel": "",
    "embeddingAiModelConfigId": null
  }
};

import { useEffect, useMemo, useState } from 'react'
import { NodePanelTabGate } from '@/components/node-panel/NodePanelTabContext'
import type { GraphPanelContext, ProjectAiModelOption } from '@/components/NodePanel'
import { FieldLabel } from '@/components/node-panel/FieldLabel'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  INVALID_AI_MODEL_SELECTION_VALUE as INVALID_SELECTION_VALUE,
  catalogToSelectOptions,
  hasExplicitAiModelChoice,
  resolvedAiModelSelectValue,
  type AiModelFieldKeys,
} from '@/lib/nodePanelAiModel'

const DEFAULTS = {
  prompt: '',
  descriptionModel: '',
  descriptionAiModelConfigId: null as string | null,
  embeddingModel: '',
  embeddingAiModelConfigId: null as string | null,
}

const GENERATIVE_TEXT_MODEL_CAPABILITIES = ['text', 'json'] as const

const DESCRIPTION_MODEL_KEYS: AiModelFieldKeys = {
  configIdKey: 'descriptionAiModelConfigId',
  modelKey: 'descriptionModel',
}

const EMBEDDING_MODEL_KEYS: AiModelFieldKeys = {
  configIdKey: 'embeddingAiModelConfigId',
  modelKey: 'embeddingModel',
}

interface EmbedImagesPanelProps {
  node: { id: string; data?: Record<string, unknown> }
  editMode?: boolean
  setNodes?: (updater: (nodes: unknown[]) => unknown[]) => void
  graphContext?: GraphPanelContext
}

function useCatalogRows(
  graphContext: GraphPanelContext | undefined,
  capabilities: string[],
): {
  rows: ProjectAiModelOption[]
  loading: boolean
  error: string | null
} {
  const projectId = graphContext?.projectId ?? null
  const [rows, setRows] = useState<ProjectAiModelOption[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const fetcher = graphContext?.fetchProjectAiModels
    if (projectId == null || fetcher == null) {
      setRows([])
      setError(null)
      setLoading(false)
      return
    }
    let cancelled = false
    setLoading(true)
    setError(null)
    void fetcher(capabilities)
      .then((nextRows) => {
        if (!cancelled) {
          setRows(nextRows)
          setLoading(false)
        }
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setRows([])
          setError(e instanceof Error ? e.message : 'Could not load models.')
          setLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [projectId, graphContext?.fetchProjectAiModels, capabilities.join(',')])

  return { rows, loading, error }
}

function ModelSelect({
  id,
  label,
  required,
  disabled,
  modelKeys,
  paramsRecord,
  catalogRows,
  catalogLoading,
  catalogError,
  nodeData,
  onChange,
}: {
  id: string
  label: string
  required?: boolean
  disabled: boolean
  modelKeys: AiModelFieldKeys
  paramsRecord: Record<string, unknown>
  catalogRows: ProjectAiModelOption[]
  catalogLoading: boolean
  catalogError: string | null
  nodeData: Record<string, unknown>
  onChange: (updates: Record<string, unknown>) => void
}) {
  const modelSelectOptions = useMemo(() => catalogToSelectOptions(catalogRows), [catalogRows])
  const resolvedUnderlying = resolvedAiModelSelectValue(paramsRecord, catalogRows, modelKeys)
  const selectionValid =
    resolvedUnderlying !== '' &&
    modelSelectOptions.some((option) => option.selectValue === resolvedUnderlying)

  const showInvalidPersisted =
    Boolean(!disabled && catalogRows.length > 0 && !catalogLoading) &&
    hasExplicitAiModelChoice(nodeData, modelKeys) &&
    !selectionValid

  const radixSelectValue = selectionValid
    ? resolvedUnderlying
    : showInvalidPersisted
      ? INVALID_SELECTION_VALUE
      : undefined

  return (
    <div className="space-y-2">
      <FieldLabel required={required} htmlFor={id}>
        {label}
      </FieldLabel>
      {catalogLoading ? (
        <p className="text-sm text-muted-foreground">Loading models…</p>
      ) : catalogError ? (
        <p className="text-sm text-destructive">{catalogError}</p>
      ) : modelSelectOptions.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          {modelKeys.modelKey === 'descriptionModel'
            ? 'Enable at least one text model for this project in Models.'
            : modelKeys.modelKey === 'embeddingModel'
              ? 'Enable at least one embedding model for this project in Models.'
              : 'No models available for this project.'}
        </p>
      ) : (
        <Select
          value={radixSelectValue}
          onValueChange={(selectValue) => {
            if (selectValue === INVALID_SELECTION_VALUE) return
            const hit = catalogRows.find(
              (row) => (row.configId ?? row.providerModelId) === selectValue,
            )
            onChange({
              [modelKeys.configIdKey]: hit?.configId ?? null,
              [modelKeys.modelKey]: hit?.providerModelId ?? selectValue,
            })
          }}
          disabled={disabled}
        >
          <SelectTrigger id={id} className="text-sm">
            <SelectValue placeholder={`Choose a ${label.toLowerCase()}`} />
          </SelectTrigger>
          <SelectContent>
            {showInvalidPersisted ? (
              <SelectItem value={INVALID_SELECTION_VALUE} disabled>
                Saved model is no longer available
              </SelectItem>
            ) : null}
            {modelSelectOptions.map((option) => (
              <SelectItem key={option.selectValue} value={option.selectValue}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}
    </div>
  )
}

export default function EmbedImagesPanel({
  node,
  editMode,
  setNodes,
  graphContext,
}: EmbedImagesPanelProps) {
  const merged = {
    ...DEFAULTS,
    ...(nodeMetadata.defaultParams || {}),
    ...(node.data || {}),
  }
  const paramsRecord = merged as Record<string, unknown>
  if (
    typeof paramsRecord.descriptionModel !== 'string' ||
    !String(paramsRecord.descriptionModel).trim()
  ) {
    const legacyModel = paramsRecord.visionModel
    if (typeof legacyModel === 'string' && legacyModel.trim()) {
      paramsRecord.descriptionModel = legacyModel
    }
  }
  if (paramsRecord.descriptionAiModelConfigId == null && paramsRecord.visionAiModelConfigId != null) {
    paramsRecord.descriptionAiModelConfigId = paramsRecord.visionAiModelConfigId
  }
  const disabled = !(editMode && setNodes)

  const descriptionCatalog = useCatalogRows(graphContext, [...GENERATIVE_TEXT_MODEL_CAPABILITIES])
  const embeddingCatalog = useCatalogRows(graphContext, ['embedding'])

  const descriptionOptions = useMemo(
    () => catalogToSelectOptions(descriptionCatalog.rows),
    [descriptionCatalog.rows],
  )
  const embeddingOptions = useMemo(
    () => catalogToSelectOptions(embeddingCatalog.rows),
    [embeddingCatalog.rows],
  )

  const patch = (updates: Record<string, unknown>) => {
    if (!setNodes) return
    setNodes((nds) =>
      (nds as { id: string; data?: Record<string, unknown> }[]).map((n) =>
        n.id === node.id ? { ...n, data: { ...(n.data || {}), ...updates } } : n,
      ),
    )
  }

  useEffect(() => {
    if (disabled || descriptionCatalog.loading || descriptionCatalog.rows.length === 0) return
    const data = (node.data || {}) as Record<string, unknown>
    if (hasExplicitAiModelChoice(data, DESCRIPTION_MODEL_KEYS)) return
    const first = descriptionOptions[0]
    if (!first) return
    patch({
      descriptionModel: first.providerModelId,
      descriptionAiModelConfigId: first.configId ?? null,
    })
  }, [
    disabled,
    descriptionCatalog.loading,
    descriptionCatalog.rows,
    descriptionOptions,
    node.id,
    node.data,
  ])

  useEffect(() => {
    if (disabled || embeddingCatalog.loading || embeddingCatalog.rows.length === 0) return
    const data = (node.data || {}) as Record<string, unknown>
    if (hasExplicitAiModelChoice(data, EMBEDDING_MODEL_KEYS)) return
    const first = embeddingOptions[0]
    if (!first) return
    patch({
      embeddingModel: first.providerModelId,
      embeddingAiModelConfigId: first.configId ?? null,
    })
  }, [
    disabled,
    embeddingCatalog.loading,
    embeddingCatalog.rows,
    embeddingOptions,
    node.id,
    node.data,
  ])

  const currentPrompt =
    typeof paramsRecord.prompt === 'string' && paramsRecord.prompt.trim()
      ? paramsRecord.prompt
      : String(nodeMetadata.defaultParams?.prompt || '')

  return (
    <>
      <NodePanelTabGate tab="settings">
        <div className="space-y-4">
          <ModelSelect
            id="embed-images-description-model"
            label="Description model"
            required
            disabled={disabled}
            modelKeys={DESCRIPTION_MODEL_KEYS}
            paramsRecord={paramsRecord}
            catalogRows={descriptionCatalog.rows}
            catalogLoading={descriptionCatalog.loading}
            catalogError={descriptionCatalog.error}
            nodeData={(node.data || {}) as Record<string, unknown>}
            onChange={patch}
          />
          <ModelSelect
            id="embed-images-embedding-model"
            label="Embedding model"
            required
            disabled={disabled}
            modelKeys={EMBEDDING_MODEL_KEYS}
            paramsRecord={paramsRecord}
            catalogRows={embeddingCatalog.rows}
            catalogLoading={embeddingCatalog.loading}
            catalogError={embeddingCatalog.error}
            nodeData={(node.data || {}) as Record<string, unknown>}
            onChange={patch}
          />
          <div className="space-y-2">
            <Label htmlFor="embed-images-prompt" className="text-sm font-medium">
              Description prompt
            </Label>
            {disabled ? (
              <p className="text-sm text-muted-foreground whitespace-pre-wrap">{currentPrompt}</p>
            ) : (
              <Textarea
                id="embed-images-prompt"
                value={currentPrompt}
                onChange={(e) => patch({ prompt: e.target.value })}
                className="min-h-[120px] text-xs font-mono"
              />
            )}
            <p className="text-xs text-muted-foreground">
              Caption, alt text, and article text from upstream inputs are added automatically as
              context. The model does not see the image itself.
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
    </>
  )
}
