// Auto-injected metadata for GeocodeAgent
const nodeMetadata = {
  "type": "GeocodeAgent",
  "label": "Geocode Agent",
  "icon": "MapPin",
  "color": "bg-emerald-500",
  "description": "Intelligent geocoding using LLM reasoning (ported from agate-ai-platform).",
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
    "projectSlug": ""
  }
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
}

interface GeocodeAgentPanelProps {
  node: any
  onChange?: (text: string) => void
  onRun?: () => void
  running?: boolean
  currentRun?: any
  editMode?: boolean
  setNodes?: (nodes: any) => void
  graphContext?: GraphPanelContext
  /** When set, resolves `execute_graph` snake_case output keys for this graph. */
  nodeOutputLookupSpec?: NodeOutputLookupSpec | null
}

export default function GeocodeAgentPanel({
  node,
  editMode,
  setNodes,
  currentRun,
  graphContext,
  nodeOutputLookupSpec,
}: GeocodeAgentPanelProps) {
  const params = { ...DEFAULTS, ...(node.data || {}) }

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

  const handleUseCacheChange = (checked: boolean) => {
    if (setNodes) {
      setNodes((nodes: any[]) =>
        nodes.map((n) => {
          if (n.id !== node.id) return n
          const data: Record<string, unknown> = {
            ...DEFAULTS,
            ...(n.data || {}),
            useCache: checked,
          }
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
        n.id === node.id
          ? { ...n, data: { ...DEFAULTS, ...(n.data || {}), stylebookId: nextId } }
          : n,
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
          <p className="text-sm text-muted-foreground mt-1">
            This node uses LLM reasoning to intelligently geocode locations from Place Extract. It
            enhances geocoding accuracy by understanding context and resolving ambiguities.
          </p>
        </div>
      </div>

      <div className="pt-4 border-t">
        <div>
          <Label className="text-sm font-medium">Parameters</Label>
        </div>

        <div className="space-y-3 mt-2">
          <div className="pt-2 border-t">
            <div className="flex items-center space-x-2">
              <Checkbox
                id="useCache"
                checked={params.useCache || false}
                onCheckedChange={(c) => handleUseCacheChange(c === true)}
                disabled={isDisabled}
              />
              <Label htmlFor="useCache" className="text-xs font-medium cursor-pointer">
                Use Cache
              </Label>
            </div>
            <p className="text-xs text-muted-foreground mt-1 ml-6">
              Worker runs: match Stylebook canonicals and location cache in Postgres before external
              geocoding when a Stylebook is selected. Legacy HTTP Stylebook URL/slug in saved graphs
              still applies only when no DB resolver is active.
            </p>
          </div>

          {params.useCache && (
            <div className="space-y-2">
              <Label htmlFor="geocode-stylebook" className="text-xs">
                Stylebook
              </Label>
              <Select
                value={stylebookSelectValue}
                onValueChange={handleStylebookSelect}
                disabled={isDisabled || orgId == null}
              >
                <SelectTrigger id="geocode-stylebook" className="text-xs">
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
