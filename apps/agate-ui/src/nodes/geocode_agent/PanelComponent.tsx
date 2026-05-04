// Auto-injected metadata for GeocodeAgent
const nodeMetadata = {
  "type": "GeocodeAgent",
  "label": "Geocode Agent",
  "icon": "MapPin",
  "color": "bg-teal-600",
  "description": "Turns PlaceExtract output into map-ready locations: optional Stylebook cache, routing, then external geocoding. Pick models for area checks and for how each place is looked up after cache.",
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
    "useCache": false,
    "stylebook_id": null,
    "stylebookApiUrl": "",
    "projectSlug": "",
    "evaluationModel": "gpt-5-nano",
    "routerModel": "gpt-5-nano"
  },
  "availableModels": [
    {
      "value": "gpt-5.4",
      "label": "GPT 5.4"
    },
    {
      "value": "gpt-5.2",
      "label": "GPT 5.2"
    },
    {
      "value": "gpt-5-mini",
      "label": "GPT-5 Mini"
    },
    {
      "value": "gpt-5-nano",
      "label": "GPT-5 Nano"
    },
    {
      "value": "gpt-4o-mini",
      "label": "GPT-4o Mini"
    }
  ]
};

import React, { useEffect, useState } from 'react'
import type { GraphPanelContext } from '@/components/NodePanel'
import { getNodeOutputById, type NodeOutputLookupSpec } from '@/lib/nodeOutputs'
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'
import { listOrgStylebooks, type OrgStylebook } from '@/lib/core-api'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

const DEFAULTS = {
  maxLocations: 100,
  perLocationTimeout: 300,
  useCache: false,
  stylebook_id: null as number | null,
  stylebookApiUrl: '',
  projectSlug: '',
  evaluationModel: 'gpt-5-nano',
  routerModel: 'gpt-5-nano',
}

const PANEL_DESCRIPTION =
  'Turns extracted places into map-ready results: optional location cache, smart routing, then external geocoding. Pick models for area checks and for how each place is looked up after cache.'

/** Same options as ``metadata.json`` ``availableModels`` (sync-nodes also injects ``nodeMetadata`` for the app). */
const AVAILABLE_MODELS = [
  { value: 'gpt-5.4', label: 'GPT 5.4' },
  { value: 'gpt-5.2', label: 'GPT 5.2' },
  { value: 'gpt-5-mini', label: 'GPT-5 Mini' },
  { value: 'gpt-5-nano', label: 'GPT-5 Nano' },
  { value: 'gpt-4o-mini', label: 'GPT-4o Mini' },
]

interface GeocodeAgentPanelProps {
  node: any
  onChange?: (text: string) => void
  onRun?: () => void
  running?: boolean
  currentRun?: any
  editMode?: boolean
  setNodes?: (nodes: any) => void
  graphContext?: GraphPanelContext
  nodeOutputLookupSpec?: NodeOutputLookupSpec | null
}

/** Prefer canonical ``stylebook_id``; legacy persisted ``stylebookId`` is still read once. */
function resolvedStylebookId(data: Record<string, unknown> | undefined): number | null {
  const d = data || {}
  const snake = d.stylebook_id
  const camel = d.stylebookId
  const raw = snake !== undefined && snake !== null ? snake : camel
  if (raw === null || raw === undefined || raw === '') return null
  const n = typeof raw === 'number' ? raw : Number(raw)
  return Number.isFinite(n) ? n : null
}

export default function GeocodeAgentPanel({
  node,
  editMode,
  setNodes,
  currentRun,
  graphContext,
  nodeOutputLookupSpec,
}: GeocodeAgentPanelProps) {
  const merged = { ...DEFAULTS, ...(node.data || {}) }
  const legacyCamel = (node.data as Record<string, unknown> | undefined)?.stylebookId
  if (merged.stylebook_id == null && legacyCamel != null && legacyCamel !== '') {
    ;(merged as Record<string, unknown>).stylebook_id = legacyCamel
  }
  const params = merged

  const modelOptions = AVAILABLE_MODELS

  const isDisabled = !(editMode && setNodes)
  const orgId = graphContext?.organizationId ?? null
  const [stylebooks, setStylebooks] = useState<OrgStylebook[]>([])
  const [stylebooksError, setStylebooksError] = useState<string | null>(null)

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
          setStylebooksError(e instanceof Error ? e.message : 'Could not load catalogs.')
        }
      })
    return () => {
      cancelled = true
    }
  }, [orgId, params.useCache])

  const mergeData = (base: Record<string, unknown>) => {
    const out = {
      ...DEFAULTS,
      ...base,
    }
    delete (out as { stylebookId?: unknown }).stylebookId
    return out
  }

  /** When cache is on, ensure a concrete catalog id (no empty selection). */
  useEffect(() => {
    if (!editMode || !setNodes || !params.useCache) return
    const cur = resolvedStylebookId(node.data as Record<string, unknown>)
    if (cur != null) return
    const fallback =
      graphContext?.workspaceDefaultStylebookId ??
      stylebooks.find((s) => s.is_default)?.id ??
      stylebooks[0]?.id
    if (fallback == null) return
    setNodes((nodes: any[]) =>
      nodes.map((n) =>
        n.id === node.id
          ? {
              ...n,
              data: mergeData({ ...(n.data || {}), stylebook_id: fallback }),
            }
          : n,
      ),
    )
  }, [editMode, setNodes, params.useCache, node.id, node.data, graphContext?.workspaceDefaultStylebookId, stylebooks])

  const handleUseCacheChange = (checked: boolean) => {
    if (setNodes) {
      setNodes((nodes: any[]) =>
        nodes.map((n) => {
          if (n.id !== node.id) return n
          const data = mergeData({ ...(n.data || {}), useCache: checked })
          const sid = resolvedStylebookId(data as Record<string, unknown>)
          if (checked && sid == null && graphContext?.workspaceDefaultStylebookId != null) {
            data.stylebook_id = graphContext.workspaceDefaultStylebookId
          }
          if (!checked) {
            data.stylebook_id = null
          }
          return { ...n, data }
        }),
      )
    }
  }

  const paramStylebookId = resolvedStylebookId(params as Record<string, unknown>)
  const stylebookSelectValue =
    paramStylebookId != null ? String(paramStylebookId) : ''

  const handleStylebookSelect = (value: string) => {
    if (!setNodes) return
    const nextId = Number(value)
    setNodes((nodes: any[]) =>
      nodes.map((n) =>
        n.id === node.id
          ? { ...n, data: mergeData({ ...(n.data || {}), stylebook_id: nextId }) }
          : n,
      ),
    )
  }

  const handleEvaluationModel = (value: string) => {
    if (!setNodes) return
    setNodes((nodes: any[]) =>
      nodes.map((n) =>
        n.id === node.id ? { ...n, data: mergeData({ ...(n.data || {}), evaluationModel: value }) } : n,
      ),
    )
  }

  const handleRouterModel = (value: string) => {
    if (!setNodes) return
    setNodes((nodes: any[]) =>
      nodes.map((n) =>
        n.id === node.id ? { ...n, data: mergeData({ ...(n.data || {}), routerModel: value }) } : n,
      ),
    )
  }

  const nodeOutput = getNodeOutputById(
    currentRun?.node_outputs as Record<string, unknown> | undefined,
    node.id,
    nodeOutputLookupSpec ?? undefined,
  )
  const latestData: Record<string, unknown> | null =
    nodeOutput != null && typeof nodeOutput === 'object' ? (nodeOutput as Record<string, unknown>) : null
  const places = latestData?.places as
    | {
        areas?: Record<string, unknown[]>
        points?: unknown[]
        needs_review?: unknown[]
      }
    | undefined
  const areaTotal =
    places?.areas != null
      ? Object.values(places.areas).reduce((n, arr) => n + (Array.isArray(arr) ? arr.length : 0), 0)
      : 0
  const pointCount = Array.isArray(places?.points) ? places.points.length : 0
  const reviewCount = Array.isArray(places?.needs_review) ? places.needs_review.length : 0
  const locationsRaw = latestData?.locations
  const locationsList: unknown[] = Array.isArray(locationsRaw) ? locationsRaw : []
  const locationCount = areaTotal + pointCount + reviewCount || locationsList.length
  const sampleSnippet =
    places != null
      ? JSON.stringify(places, null, 2)
      : locationsList[0] != null
        ? JSON.stringify(locationsList[0], null, 2)
        : ''

  return (
    <>
      <div className="space-y-3">
        <div>
          <Label className="text-sm font-medium">Description</Label>
          <p className="text-sm text-muted-foreground mt-1">{PANEL_DESCRIPTION}</p>
        </div>
      </div>

      <div className="pt-4 border-t">
        <div>
          <Label className="text-sm font-medium">Parameters</Label>
        </div>

        <div className="space-y-3 mt-2">
          <div className="space-y-2">
            <Label className="text-xs">Evaluation model</Label>
            <Select
              value={String(params.evaluationModel)}
              onValueChange={handleEvaluationModel}
              disabled={isDisabled}
            >
              <SelectTrigger className="text-xs">
                <SelectValue placeholder="Model" />
              </SelectTrigger>
              <SelectContent>
                {modelOptions.map((m) => (
                  <SelectItem key={m.value} value={m.value}>
                    {m.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              Used when the area geocoder asks the model to judge ambiguous map results.
            </p>
          </div>

          <div className="space-y-2">
            <Label className="text-xs">Routing model</Label>
            <Select
              value={String(params.routerModel)}
              onValueChange={handleRouterModel}
              disabled={isDisabled}
            >
              <SelectTrigger className="text-xs">
                <SelectValue placeholder="Model" />
              </SelectTrigger>
              <SelectContent>
                {modelOptions.map((m) => (
                  <SelectItem key={`r-${m.value}`} value={m.value}>
                    {m.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              Model used after cache check to choose how each place is looked up (web vs structured only). Run
              records can include a short audit for support.
            </p>
          </div>

          <div className="pt-2 border-t">
            <div className="flex items-center space-x-2">
              <Checkbox
                id="geocode-useCache"
                checked={params.useCache || false}
                onCheckedChange={(c) => handleUseCacheChange(c === true)}
                disabled={isDisabled}
              />
              <Label htmlFor="geocode-useCache" className="text-xs font-medium cursor-pointer">
                Use cache
              </Label>
            </div>
            <p className="text-xs text-muted-foreground mt-1 ml-6">
              Worker runs: match catalog locations and location cache before external geocoding when a catalog is
              selected.
            </p>
          </div>

          {params.useCache && (
            <div className="space-y-2">
              <Label htmlFor="geocode-stylebook" className="text-xs">
                Catalog
              </Label>
              <Select
                value={stylebookSelectValue}
                onValueChange={handleStylebookSelect}
                disabled={isDisabled || orgId == null || stylebooks.length === 0}
              >
                <SelectTrigger id="geocode-stylebook" className="text-xs">
                  <SelectValue placeholder="Choose a catalog" />
                </SelectTrigger>
                <SelectContent>
                  {stylebooks.map((sb) => (
                    <SelectItem key={sb.id} value={String(sb.id)}>
                      {sb.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {orgId == null && (
                <p className="text-xs text-muted-foreground">
                  Save the flow to a project (or open an existing project flow) to load catalogs for your
                  organization.
                </p>
              )}
              {orgId != null && params.useCache && stylebooks.length === 0 && !stylebooksError && (
                <p className="text-xs text-muted-foreground">Loading catalogs…</p>
              )}
              {stylebooksError && <p className="text-xs text-destructive">{stylebooksError}</p>}
            </div>
          )}
        </div>
      </div>

      {latestData && (
        <div className="pt-4 border-t">
          <Label className="text-sm font-medium">Latest run</Label>
          <div className="mt-2 space-y-2">
            <div className="text-xs text-muted-foreground">
              <div>
                Geocoded {locationCount} location{locationCount !== 1 ? 's' : ''}
              </div>
            </div>

            {locationCount > 0 && sampleSnippet && (
              <div>
                <Label className="text-xs font-medium">Sample output</Label>
                <div className="text-xs font-mono p-2 bg-muted rounded mt-1 max-h-32 overflow-y-auto">
                  {sampleSnippet.substring(0, 200)}
                  {sampleSnippet.length > 200 ? '...' : ''}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  )
}
