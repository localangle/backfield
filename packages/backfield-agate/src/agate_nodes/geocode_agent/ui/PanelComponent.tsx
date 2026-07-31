import { useEffect, useMemo, useState } from 'react'
import { NodePanelTabGate } from '@/components/node-panel/NodePanelTabContext'
import type { GraphPanelContext, ProjectAiModelOption } from '@/components/NodePanel'
import { Label } from '@/components/ui/label'
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
} from '@/lib/nodePanelAiModel'

const DEFAULTS = {
  maxLocations: 200,
  perLocationTimeout: 300,
  useCache: true,
  stylebookApiUrl: '',
  projectSlug: '',
  evaluationModel: '',
  geographicReasoningModel: '',
  geographicEstimationModel: '',
  routerModel: '',
  evaluationAiModelConfigId: null as string | null,
  geographicReasoningAiModelConfigId: null as string | null,
  geographicEstimationAiModelConfigId: null as string | null,
  routerAiModelConfigId: null as string | null,
  useCacheLlmAdjudication: true,
  useCacheLlmAdjudicationOnMissRecall: false,
}

const EVALUATION_MODEL_KEYS = {
  configIdKey: 'evaluationAiModelConfigId',
  modelKey: 'evaluationModel',
} as const

const ROUTER_MODEL_KEYS = {
  configIdKey: 'routerAiModelConfigId',
  modelKey: 'routerModel',
} as const

const GEOGRAPHIC_REASONING_MODEL_KEYS = {
  configIdKey: 'geographicReasoningAiModelConfigId',
  modelKey: 'geographicReasoningModel',
} as const

const GEOGRAPHIC_ESTIMATION_MODEL_KEYS = {
  configIdKey: 'geographicEstimationAiModelConfigId',
  modelKey: 'geographicEstimationModel',
} as const

function resolvedEvaluationSelectValue(
  params: Record<string, unknown>,
  catalog: ProjectAiModelOption[],
): string {
  return resolvedAiModelSelectValue(params, catalog, EVALUATION_MODEL_KEYS)
}

function resolvedRouterSelectValue(
  params: Record<string, unknown>,
  catalog: ProjectAiModelOption[],
): string {
  return resolvedAiModelSelectValue(params, catalog, ROUTER_MODEL_KEYS)
}

function hasExplicitEvaluationChoice(data: Record<string, unknown>): boolean {
  return hasExplicitAiModelChoice(data, EVALUATION_MODEL_KEYS)
}

function hasExplicitRouterChoice(data: Record<string, unknown>): boolean {
  return hasExplicitAiModelChoice(data, ROUTER_MODEL_KEYS)
}

function resolvedGeographicReasoningSelectValue(
  params: Record<string, unknown>,
  catalog: ProjectAiModelOption[],
): string {
  return resolvedAiModelSelectValue(params, catalog, GEOGRAPHIC_REASONING_MODEL_KEYS)
}

function hasExplicitGeographicReasoningChoice(data: Record<string, unknown>): boolean {
  return hasExplicitAiModelChoice(data, GEOGRAPHIC_REASONING_MODEL_KEYS)
}

function resolvedGeographicEstimationSelectValue(
  params: Record<string, unknown>,
  catalog: ProjectAiModelOption[],
): string {
  return resolvedAiModelSelectValue(params, catalog, GEOGRAPHIC_ESTIMATION_MODEL_KEYS)
}

function hasExplicitGeographicEstimationChoice(data: Record<string, unknown>): boolean {
  return hasExplicitAiModelChoice(data, GEOGRAPHIC_ESTIMATION_MODEL_KEYS)
}

interface GeocodeAgentPanelProps {
  node: any
  editMode?: boolean
  setNodes?: (nodes: any) => void
  graphContext?: GraphPanelContext
}

export default function GeocodeAgentPanel({
  node,
  editMode,
  setNodes,
  graphContext,
}: GeocodeAgentPanelProps) {
  const merged = { ...DEFAULTS, ...(node.data || {}) }
  const params = merged

  const isDisabled = !(editMode && setNodes)
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

  const paramsRecord = params as Record<string, unknown>

  const modelSelectOptions = useMemo(() => catalogToSelectOptions(catalogRows), [catalogRows])

  const resolvedEval = resolvedEvaluationSelectValue(paramsRecord, catalogRows)
  const resolvedRouter = resolvedRouterSelectValue(paramsRecord, catalogRows)
  const resolvedGeo = resolvedGeographicReasoningSelectValue(paramsRecord, catalogRows)
  const resolvedGeoEst = resolvedGeographicEstimationSelectValue(paramsRecord, catalogRows)

  const evalSelectionValid =
    resolvedEval !== '' && modelSelectOptions.some((o) => o.selectValue === resolvedEval)
  const routerSelectionValid =
    resolvedRouter !== '' && modelSelectOptions.some((o) => o.selectValue === resolvedRouter)
  const geoSelectionValid =
    resolvedGeo !== '' && modelSelectOptions.some((o) => o.selectValue === resolvedGeo)
  const geoEstSelectionValid =
    resolvedGeoEst !== '' && modelSelectOptions.some((o) => o.selectValue === resolvedGeoEst)

  const nodeDataFlat = (node.data || {}) as Record<string, unknown>

  const showInvalidEvalPersisted =
    Boolean(editMode && setNodes && projectId != null && catalogRows.length > 0 && !catalogLoading) &&
    hasExplicitEvaluationChoice(nodeDataFlat) &&
    !evalSelectionValid

  const showInvalidRouterPersisted =
    Boolean(editMode && setNodes && projectId != null && catalogRows.length > 0 && !catalogLoading) &&
    hasExplicitRouterChoice(nodeDataFlat) &&
    !routerSelectionValid

  const showInvalidGeoPersisted =
    Boolean(editMode && setNodes && projectId != null && catalogRows.length > 0 && !catalogLoading) &&
    hasExplicitGeographicReasoningChoice(nodeDataFlat) &&
    !geoSelectionValid

  const showInvalidGeoEstPersisted =
    Boolean(editMode && setNodes && projectId != null && catalogRows.length > 0 && !catalogLoading) &&
    hasExplicitGeographicEstimationChoice(nodeDataFlat) &&
    !geoEstSelectionValid

  const evalRadixValue = evalSelectionValid
    ? resolvedEval
    : showInvalidEvalPersisted
      ? INVALID_SELECTION_VALUE
      : undefined

  const routerRadixValue = routerSelectionValid
    ? resolvedRouter
    : showInvalidRouterPersisted
      ? INVALID_SELECTION_VALUE
      : undefined

  const geoRadixValue = geoSelectionValid
    ? resolvedGeo
    : showInvalidGeoPersisted
      ? INVALID_SELECTION_VALUE
      : undefined

  const geoEstRadixValue = geoEstSelectionValid
    ? resolvedGeoEst
    : showInvalidGeoEstPersisted
      ? INVALID_SELECTION_VALUE
      : undefined

  const mergeData = (base: Record<string, unknown>) => {
    const out = {
      ...DEFAULTS,
      ...base,
    }
    delete (out as { stylebookId?: unknown }).stylebookId
    return out
  }

  /** Fill missing model picks from the effective catalog once it loads (no silent built-in presets). */
  useEffect(() => {
    if (!editMode || !setNodes || catalogLoading || catalogRows.length === 0) return
    const data = nodeDataFlat
    const needEval = !hasExplicitEvaluationChoice(data)
    const needRouter = !hasExplicitRouterChoice(data)
    const needGeo = !hasExplicitGeographicReasoningChoice(data)
    const needGeoEst = !hasExplicitGeographicEstimationChoice(data)
    if (!needEval && !needRouter && !needGeo && !needGeoEst) return
    const first = modelSelectOptions[0]
    if (!first) return
    const patch: Record<string, unknown> = {}
    if (needEval) {
      patch.evaluationModel = first.providerModelId
      patch.evaluationAiModelConfigId = first.configId ?? null
    }
    if (needRouter) {
      patch.routerModel = first.providerModelId
      patch.routerAiModelConfigId = first.configId ?? null
    }
    if (needGeo) {
      patch.geographicReasoningModel = first.providerModelId
      patch.geographicReasoningAiModelConfigId = first.configId ?? null
    }
    if (needGeoEst) {
      patch.geographicEstimationModel = first.providerModelId
      patch.geographicEstimationAiModelConfigId = first.configId ?? null
    }
    setNodes((nodes: any[]) =>
      nodes.map((n) =>
        n.id === node.id
          ? {
              ...n,
              data: mergeData({ ...(n.data || {}), ...patch }),
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

  const handleUseCacheChange = (checked: boolean) => {
    if (setNodes) {
      setNodes((nodes: any[]) =>
        nodes.map((n) =>
          n.id === node.id
            ? { ...n, data: mergeData({ ...(n.data || {}), useCache: checked }) }
            : n,
        ),
      )
    }
  }

  const handleEvaluationModel = (selectValue: string) => {
    if (!setNodes || selectValue === INVALID_SELECTION_VALUE) return
    const row = modelSelectOptions.find((o) => o.selectValue === selectValue)
    const providerModelId = row?.providerModelId ?? selectValue
    const configId = row?.configId
    setNodes((nodes: any[]) =>
      nodes.map((n) =>
        n.id === node.id
          ? {
              ...n,
              data: mergeData({
                ...(n.data || {}),
                evaluationModel: providerModelId,
                evaluationAiModelConfigId: configId ?? null,
              }),
            }
          : n,
      ),
    )
  }

  const handleRouterModel = (selectValue: string) => {
    if (!setNodes || selectValue === INVALID_SELECTION_VALUE) return
    const row = modelSelectOptions.find((o) => o.selectValue === selectValue)
    const providerModelId = row?.providerModelId ?? selectValue
    const configId = row?.configId
    setNodes((nodes: any[]) =>
      nodes.map((n) =>
        n.id === node.id
          ? {
              ...n,
              data: mergeData({
                ...(n.data || {}),
                routerModel: providerModelId,
                routerAiModelConfigId: configId ?? null,
              }),
            }
          : n,
      ),
    )
  }

  const handleGeographicReasoningModel = (selectValue: string) => {
    if (!setNodes || selectValue === INVALID_SELECTION_VALUE) return
    const row = modelSelectOptions.find((o) => o.selectValue === selectValue)
    const providerModelId = row?.providerModelId ?? selectValue
    const configId = row?.configId
    setNodes((nodes: any[]) =>
      nodes.map((n) =>
        n.id === node.id
          ? {
              ...n,
              data: mergeData({
                ...(n.data || {}),
                geographicReasoningModel: providerModelId,
                geographicReasoningAiModelConfigId: configId ?? null,
              }),
            }
          : n,
      ),
    )
  }

  const handleGeographicEstimationModel = (selectValue: string) => {
    if (!setNodes || selectValue === INVALID_SELECTION_VALUE) return
    const row = modelSelectOptions.find((o) => o.selectValue === selectValue)
    const providerModelId = row?.providerModelId ?? selectValue
    const configId = row?.configId
    setNodes((nodes: any[]) =>
      nodes.map((n) =>
        n.id === node.id
          ? {
              ...n,
              data: mergeData({
                ...(n.data || {}),
                geographicEstimationModel: providerModelId,
                geographicEstimationAiModelConfigId: configId ?? null,
              }),
            }
          : n,
      ),
    )
  }

  const catalogHint =
    (projectId == null || graphContext?.fetchProjectAiModels == null) && editMode ? (
      <p className="text-xs text-muted-foreground">
        Save this flow under a project to choose models your organization enabled for this project.
      </p>
    ) : null

  const catalogEmptyHint =
    !catalogLoading &&
    !catalogError &&
    projectId != null &&
    graphContext?.fetchProjectAiModels != null &&
    modelSelectOptions.length === 0 ? (
      <p className="text-xs text-muted-foreground">
        No models available for this project yet. Ask an administrator to enable models for your organization, then turn
        them on for this project in project settings if needed.
      </p>
    ) : null

  return (
    <>
      <NodePanelTabGate tab="settings">
        <div className="space-y-3">
          <div className="space-y-2">
            <Label htmlFor="geocode-useCache" className="text-sm font-medium">
              Use cache
            </Label>
            <Select
              value={params.useCache ? 'yes' : 'no'}
              onValueChange={(value) => handleUseCacheChange(value === 'yes')}
              disabled={isDisabled}
            >
              <SelectTrigger id="geocode-useCache" className="text-xs">
                <SelectValue placeholder="Choose whether to use cache" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="yes">Yes</SelectItem>
                <SelectItem value="no">No</SelectItem>
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              First attempt to use Stylebook and internal cache to retrieve coordinates.
            </p>
          </div>

        </div>
      </NodePanelTabGate>

      <NodePanelTabGate tab="models">
        <div className="space-y-3">
          <div className="space-y-2">
            <Label className="text-sm font-medium">Routing</Label>
            {catalogHint}
            {projectId != null && catalogLoading && (
              <p className="text-xs text-muted-foreground">Loading models…</p>
            )}
            {catalogError ? <p className="text-xs text-destructive">{catalogError}</p> : null}
            {catalogEmptyHint}
            {showInvalidRouterPersisted ? (
              <p className="text-xs text-muted-foreground">
                The saved routing model is no longer available. Choose another model below.
              </p>
            ) : null}
            <Select
              value={routerRadixValue}
              onValueChange={handleRouterModel}
              disabled={isDisabled || modelSelectOptions.length === 0}
            >
              <SelectTrigger className="text-xs">
                <SelectValue placeholder="Choose a model" />
              </SelectTrigger>
              <SelectContent>
                {showInvalidRouterPersisted ? (
                  <SelectItem disabled value={INVALID_SELECTION_VALUE}>
                    Saved model unavailable
                  </SelectItem>
                ) : null}
                {modelSelectOptions.map((m) => (
                  <SelectItem key={`rt-${m.selectValue}`} value={m.selectValue}>
                    {m.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              Chooses the best geocoding strategy. Small, fast models work best.
            </p>
          </div>

          <div className="space-y-2">
            <Label className="text-sm font-medium">Geographic reasoning</Label>
            {showInvalidGeoPersisted ? (
              <p className="text-xs text-muted-foreground">
                The saved geographic reasoning model is no longer available. Choose another model below.
              </p>
            ) : null}
            <Select
              value={geoRadixValue}
              onValueChange={handleGeographicReasoningModel}
              disabled={isDisabled || modelSelectOptions.length === 0}
            >
              <SelectTrigger className="text-xs">
                <SelectValue placeholder="Choose a model" />
              </SelectTrigger>
              <SelectContent>
                {showInvalidGeoPersisted ? (
                  <SelectItem disabled value={INVALID_SELECTION_VALUE}>
                    Saved model unavailable
                  </SelectItem>
                ) : null}
                {modelSelectOptions.map((m) => (
                  <SelectItem key={`geo-${m.selectValue}`} value={m.selectValue}>
                    {m.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              Performs research and evaluates geographic decisions during external geocode. Medium-sized models work best.
            </p>
          </div>

          <div className="space-y-2">
            <Label className="text-sm font-medium">Geographic estimation</Label>
            {showInvalidGeoEstPersisted ? (
              <p className="text-xs text-muted-foreground">
                The saved geographic estimation model is no longer available. Choose another model below.
              </p>
            ) : null}
            <Select
              value={geoEstRadixValue}
              onValueChange={handleGeographicEstimationModel}
              disabled={isDisabled || modelSelectOptions.length === 0}
            >
              <SelectTrigger className="text-xs">
                <SelectValue placeholder="Choose a model" />
              </SelectTrigger>
              <SelectContent>
                {showInvalidGeoEstPersisted ? (
                  <SelectItem disabled value={INVALID_SELECTION_VALUE}>
                    Saved model unavailable
                  </SelectItem>
                ) : null}
                {modelSelectOptions.map((m) => (
                  <SelectItem key={`geo-est-${m.selectValue}`} value={m.selectValue}>
                    {m.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              Estimates coordinates and boundaries when geocoders cannot resolve a location. Larger models with spatial reasoning work best.
            </p>
          </div>

          <div className="space-y-2">
            <Label className="text-sm font-medium">Evaluation</Label>
            {showInvalidEvalPersisted ? (
              <p className="text-xs text-muted-foreground">
                The saved evaluation model is no longer available. Choose another model below.
              </p>
            ) : null}
            <Select
              value={evalRadixValue}
              onValueChange={handleEvaluationModel}
              disabled={isDisabled || modelSelectOptions.length === 0}
            >
              <SelectTrigger className="text-xs">
                <SelectValue placeholder="Choose a model" />
              </SelectTrigger>
              <SelectContent>
                {showInvalidEvalPersisted ? (
                  <SelectItem disabled value={INVALID_SELECTION_VALUE}>
                    Saved model unavailable
                  </SelectItem>
                ) : null}
                {modelSelectOptions.map((m) => (
                  <SelectItem key={`ev-${m.selectValue}`} value={m.selectValue}>
                    {m.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              Decides the best candidate when geocoding results are ambiguous. Small, fast models work best.
            </p>
          </div>
        </div>
      </NodePanelTabGate>
    </>
  )
}
