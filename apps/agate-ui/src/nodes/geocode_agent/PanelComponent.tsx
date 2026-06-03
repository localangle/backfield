// Auto-injected metadata for GeocodeAgent
const nodeMetadata = {
  "type": "GeocodeAgent",
  "label": "Geocode Agent",
  "icon": "MapPinned",
  "color": "bg-teal-600",
  "description": "Requires PlaceExtract output. Uses multiple geocoders to turn extracted locations into map-ready coordinates. Optionally use cache to reduce lookups and ensure consistency.",
  "category": "enrichment",
  "requiredUpstreamNodes": [
    "PlaceExtract"
  ],
  "dependencyHelperText": "Requires extracted places as input.",
  "inputs": [
    {
      "id": "locations",
      "label": "Locations",
      "type": "array",
      "required": true
    }
  ],
  "outputs": [
    {
      "id": "places",
      "label": "Places",
      "type": "object"
    },
    {
      "id": "text",
      "label": "Text",
      "type": "string"
    }
  ],
  "defaultParams": {
    "maxLocations": 100,
    "perLocationTimeout": 300,
    "useCache": true,
    "stylebook_id": null,
    "stylebookApiUrl": "",
    "projectSlug": "",
    "evaluationModel": "",
    "geographicReasoningModel": "",
    "routerModel": "",
    "evaluationAiModelConfigId": null,
    "geographicReasoningAiModelConfigId": null,
    "routerAiModelConfigId": null,
    "useCacheLlmAdjudication": true,
    "useCacheLlmAdjudicationOnMissRecall": false
  }
};

import { useEffect, useMemo, useState } from 'react'
import { NodePanelTabGate } from '@/components/node-panel/NodePanelTabContext'
import type { GraphPanelContext, ProjectAiModelOption } from '@/components/NodePanel'
import { Label } from '@/components/ui/label'
import { listOrgStylebooks, type OrgStylebook } from '@/lib/core-api'
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
  resolvedStylebookId,
} from '@/lib/nodePanelAiModel'

const NO_STYLEBOOK_VALUE = '__bf_no_stylebook__'

const DEFAULTS = {
  maxLocations: 100,
  perLocationTimeout: 300,
  useCache: true,
  stylebook_id: null as number | null,
  stylebookApiUrl: '',
  projectSlug: '',
  evaluationModel: '',
  geographicReasoningModel: '',
  routerModel: '',
  evaluationAiModelConfigId: null as string | null,
  geographicReasoningAiModelConfigId: null as string | null,
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
  const legacyCamel = (node.data as Record<string, unknown> | undefined)?.stylebookId
  if (merged.stylebook_id == null && legacyCamel != null && legacyCamel !== '') {
    ;(merged as Record<string, unknown>).stylebook_id = legacyCamel
  }
  const params = merged

  const isDisabled = !(editMode && setNodes)
  const orgId = graphContext?.organizationId ?? null
  const projectId = graphContext?.projectId ?? null
  const [stylebooks, setStylebooks] = useState<OrgStylebook[]>([])
  const [stylebooksError, setStylebooksError] = useState<string | null>(null)
  const [catalogRows, setCatalogRows] = useState<ProjectAiModelOption[]>([])
  const [catalogLoading, setCatalogLoading] = useState(false)
  const [catalogError, setCatalogError] = useState<string | null>(null)

  useEffect(() => {
    if (!orgId || !params.useCache) {
      setStylebooks([])
      setStylebooksError(null)
      return
    }
    let cancelled = false
    setStylebooksError(null)
    listOrgStylebooks(orgId)
      .then((rows) => {
        if (!cancelled) setStylebooks(rows)
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setStylebooks([])
          setStylebooksError(e instanceof Error ? e.message : 'Could not load Stylebooks.')
        }
      })
    return () => {
      cancelled = true
    }
  }, [orgId, params.useCache])

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

  const evalSelectionValid =
    resolvedEval !== '' && modelSelectOptions.some((o) => o.selectValue === resolvedEval)
  const routerSelectionValid =
    resolvedRouter !== '' && modelSelectOptions.some((o) => o.selectValue === resolvedRouter)
  const geoSelectionValid =
    resolvedGeo !== '' && modelSelectOptions.some((o) => o.selectValue === resolvedGeo)

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
    if (!needEval && !needRouter && !needGeo) return
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
        nodes.map((n) => {
          if (n.id !== node.id) return n
          const data = mergeData({ ...(n.data || {}), useCache: checked })
          if (!checked) {
            data.stylebook_id = null
          }
          return { ...n, data }
        }),
      )
    }
  }

  const paramStylebookId = resolvedStylebookId(params as Record<string, unknown>)
  const orgDefaultStylebook = stylebooks.find((sb) => sb.is_default)
  const missingStylebookFromList =
    params.useCache &&
    paramStylebookId != null &&
    !stylebooks.some((s) => s.id === paramStylebookId)

  useEffect(() => {
    if (!editMode || !setNodes || !missingStylebookFromList || paramStylebookId == null) return
    if (stylebooks.length === 0) return
    const nextId = orgDefaultStylebook?.id ?? null
    if (nextId == null) return
    setNodes((nodes: any[]) =>
      nodes.map((n) =>
        n.id === node.id
          ? { ...n, data: mergeData({ ...(n.data || {}), stylebook_id: nextId }) }
          : n,
      ),
    )
  }, [
    editMode,
    setNodes,
    missingStylebookFromList,
    paramStylebookId,
    stylebooks.length,
    orgDefaultStylebook?.id,
    node.id,
  ])

  const stylebookSelectValue =
    paramStylebookId != null ? String(paramStylebookId) : NO_STYLEBOOK_VALUE

  const handleStylebookSelect = (value: string) => {
    if (!setNodes) return
    if (value === NO_STYLEBOOK_VALUE) {
      setNodes((nodes: any[]) =>
        nodes.map((n) =>
          n.id === node.id
            ? { ...n, data: mergeData({ ...(n.data || {}), stylebook_id: null }) }
            : n,
        ),
      )
      return
    }
    const nextId = Number(value)
    setNodes((nodes: any[]) =>
      nodes.map((n) =>
        n.id === node.id
          ? { ...n, data: mergeData({ ...(n.data || {}), stylebook_id: nextId }) }
          : n,
      ),
    )
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

          {params.useCache && (
            <div className="space-y-2">
              <Label htmlFor="geocode-stylebook" className="text-sm font-medium">
                Stylebook
              </Label>
              <Select
                value={stylebookSelectValue}
                onValueChange={handleStylebookSelect}
                disabled={isDisabled}
              >
                <SelectTrigger id="geocode-stylebook" className="text-xs">
                  <SelectValue placeholder="Choose a Stylebook" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={NO_STYLEBOOK_VALUE}>None</SelectItem>
                  {stylebooks.map((sb) => (
                    <SelectItem key={sb.id} value={String(sb.id)}>
                      {sb.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {orgId == null && (
                <p className="text-xs text-muted-foreground">
                  Save the flow to a project to load Stylebooks for your organization.
                </p>
              )}
              {orgId != null && params.useCache && stylebooks.length === 0 && !stylebooksError && (
                <p className="text-xs text-muted-foreground">Loading Stylebooks…</p>
              )}
              {stylebooksError && <p className="text-xs text-destructive">{stylebooksError}</p>}
            </div>
          )}
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
              Performs research, evaluates geographic decisions and approximates boundaries in some cases. Medium-sized models work best.
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
