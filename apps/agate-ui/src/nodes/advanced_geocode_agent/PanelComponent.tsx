// Auto-injected metadata for AdvancedGeocodeAgent
const nodeMetadata = {
  "type": "AdvancedGeocodeAgent",
  "label": "Advanced Geocode Agent",
  "icon": "MapPin",
  "color": "bg-teal-600",
  "description": "LangGraph geocoding with per-node OpenAI models: area evaluation plus post-cache route_strategy (after Stylebook/cache lookup).",
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
    "stylebookId": null,
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

const NONE_STYLEBOOK = '__none__'

const DEFAULTS = {
  maxLocations: 100,
  perLocationTimeout: 300,
  useCache: false,
  stylebookId: null as number | null,
  stylebookApiUrl: '',
  projectSlug: '',
  evaluationModel: 'gpt-5-nano',
  routerModel: 'gpt-5-nano',
}

interface AdvancedGeocodeAgentPanelProps {
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

export default function AdvancedGeocodeAgentPanel({
  node,
  editMode,
  setNodes,
  currentRun,
  graphContext,
  nodeOutputLookupSpec,
}: AdvancedGeocodeAgentPanelProps) {
  const params = { ...DEFAULTS, ...(node.data || {}) }

  const modelOptions =
    nodeMetadata.availableModels && nodeMetadata.availableModels.length > 0
      ? nodeMetadata.availableModels
      : [
          { value: 'gpt-5-nano', label: 'GPT-5 Nano' },
          { value: 'gpt-5-mini', label: 'GPT-5 Mini' },
        ]

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
          setStylebooksError(e instanceof Error ? e.message : 'Failed to load stylebooks')
        }
      })
    return () => {
      cancelled = true
    }
  }, [orgId, params.useCache])

  const mergeData = (base: Record<string, unknown>) => ({
    ...DEFAULTS,
    ...base,
  })

  const handleUseCacheChange = (checked: boolean) => {
    if (setNodes) {
      setNodes((nodes: any[]) =>
        nodes.map((n) => {
          if (n.id !== node.id) return n
          const data = mergeData({ ...(n.data || {}), useCache: checked })
          if (
            checked &&
            (data.stylebookId === null || data.stylebookId === undefined || data.stylebookId === '') &&
            graphContext?.workspaceDefaultStylebookId != null
          ) {
            data.stylebookId = graphContext.workspaceDefaultStylebookId
          }
          return { ...n, data }
        }),
      )
    }
  }

  const stylebookSelectValue =
    params.stylebookId !== null && params.stylebookId !== undefined && params.stylebookId !== ''
      ? String(params.stylebookId)
      : NONE_STYLEBOOK

  const handleStylebookSelect = (value: string) => {
    if (!setNodes) return
    const nextId = value === NONE_STYLEBOOK ? null : Number(value)
    setNodes((nodes: any[]) =>
      nodes.map((n) =>
        n.id === node.id ? { ...n, data: mergeData({ ...(n.data || {}), stylebookId: nextId }) } : n,
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
  const latestData = nodeOutput || null
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
  const locationCount =
    areaTotal + pointCount + reviewCount || (Array.isArray(latestData?.locations) ? latestData.locations.length : 0)
  const sampleSnippet =
    places != null
      ? JSON.stringify(places, null, 2)
      : latestData?.locations?.[0] != null
        ? JSON.stringify(latestData.locations[0], null, 2)
        : ''

  return (
    <>
      <div className="space-y-3">
        <div>
          <Label className="text-sm font-medium">Description</Label>
          <p className="text-sm text-muted-foreground mt-1">{nodeMetadata.description}</p>
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
              Used when the area geocoder asks the LLM to judge ambiguous Pelias / Geocodio /
              Nominatim results.
            </p>
          </div>

          <div className="space-y-2">
            <Label className="text-xs">Router model</Label>
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
              OpenAI model for the <strong className="text-foreground">route_strategy</strong> step after a cache miss (closed strategy enum; audited).
            </p>
          </div>

          <div className="pt-2 border-t">
            <div className="flex items-center space-x-2">
              <Checkbox
                id="adv-useCache"
                checked={params.useCache || false}
                onCheckedChange={(c) => handleUseCacheChange(c === true)}
                disabled={isDisabled}
              />
              <Label htmlFor="adv-useCache" className="text-xs font-medium cursor-pointer">
                Use Cache
              </Label>
            </div>
            <p className="text-xs text-muted-foreground mt-1 ml-6">
              Worker runs: match Stylebook canonicals and location cache in Postgres before external
              geocoding when a Stylebook is selected.
            </p>
          </div>

          {params.useCache && (
            <div className="space-y-2">
              <Label htmlFor="advanced-geocode-stylebook" className="text-xs">
                Stylebook
              </Label>
              <Select
                value={stylebookSelectValue}
                onValueChange={handleStylebookSelect}
                disabled={isDisabled || orgId == null}
              >
                <SelectTrigger id="advanced-geocode-stylebook" className="text-xs">
                  <SelectValue placeholder="Select a Stylebook" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={NONE_STYLEBOOK}>None</SelectItem>
                  {stylebooks.map((sb) => (
                    <SelectItem key={sb.id} value={String(sb.id)}>
                      {sb.name} ({sb.slug})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {orgId == null && (
                <p className="text-xs text-muted-foreground">
                  Save the flow to a project (or open an existing project flow) to load organization
                  Stylebooks.
                </p>
              )}
              {stylebooksError && <p className="text-xs text-destructive">{stylebooksError}</p>}
            </div>
          )}
        </div>
      </div>

      {latestData && (
        <div className="pt-4 border-t">
          <Label className="text-sm font-medium">Latest Run</Label>
          <div className="mt-2 space-y-2">
            <div className="text-xs text-muted-foreground">
              <div>
                Geocoded {locationCount} location{locationCount !== 1 ? 's' : ''}
              </div>
            </div>

            {locationCount > 0 && sampleSnippet && (
              <div>
                <Label className="text-xs font-medium">Sample Output:</Label>
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
