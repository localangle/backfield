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

import React, { useEffect, useMemo, useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { LeafletMap, LayerFilterPopover, layersFromFeatures, defaultVisibility } from '@backfield/ui'
import type { MapPointFeature, MapBoundingBoxFeature, VisualizationProps, VisualizationDescriptor } from '@/lib/visualizations'

/**
 * Build visualization descriptor for GeocodeAgent node output.
 * Returns null if no valid geocoding data is found.
 */
export function buildVisualization(
  nodeId: string,
  nodeLabel: string,
  output: any
): VisualizationDescriptor | null {
  if (!output || typeof output !== 'object') {
    return null
  }

  const places = output.places
  if (!places || typeof places !== 'object') {
    return null
  }

  // Helper functions to extract geometry data
  function toNumber(value: unknown): number | null {
    if (typeof value === 'number') return value
    if (typeof value === 'string') {
      const parsed = Number(value)
      return Number.isFinite(parsed) ? parsed : null
    }
    return null
  }

  function addPolygon(
    entry: unknown,
    fallbackId: string,
    idx: number,
    group: string,
    polygons: Array<{ 
      id: string
      bbox: [number, number, number, number]
      label?: string
      description?: string
      group?: string
      geometry?: {
        type: 'Polygon' | 'MultiPolygon'
        coordinates: number[][][] | number[][][][]
      }
    }>,
  ): void {
    if (!entry || typeof entry !== 'object') return
    const record = entry as Record<string, any>
    const geometry = record?.geocode?.result?.geometry
    if (!geometry) return
    
    const geometryType = geometry.type
    const coords = geometry.coordinates
    
    if (!geometryType || !coords) return
    
    // Check if it's a polygon type
    if (geometryType !== 'Polygon' && geometryType !== 'MultiPolygon') return
    
    // Handle MultiPolygon: [[[[lon, lat], ...], [[lon, lat], ...], ...]]
    if (geometryType === 'MultiPolygon') {
      if (!Array.isArray(coords) || coords.length === 0) {
        console.warn(`GeocodeAgent: MultiPolygon coordinates is not a valid array`, { coords, geometryType })
        return
      }
      
      let minLon = Infinity
      let maxLon = -Infinity
      let minLat = Infinity
      let maxLat = -Infinity
      
      // Iterate through all polygons in the MultiPolygon
      // MultiPolygon format: [[[[lon, lat], ...], [[lon, lat], ...], ...]
      // Each element of coords is a polygon: [[[lon, lat], ...], [[lon, lat], ...]]
      for (const polygon of coords) {
        if (!Array.isArray(polygon) || polygon.length === 0) {
          console.warn(`GeocodeAgent: Invalid polygon in MultiPolygon`, { polygon })
          continue
        }
        // First ring is the exterior ring
        const exteriorRing = polygon[0]
        if (!Array.isArray(exteriorRing)) {
          console.warn(`GeocodeAgent: Invalid exterior ring in MultiPolygon`, { exteriorRing })
          continue
        }

        for (const coord of exteriorRing) {
          if (Array.isArray(coord) && coord.length >= 2) {
            const lon = toNumber(coord[0])
            const lat = toNumber(coord[1])
            if (lon !== null && lat !== null) {
              minLon = Math.min(minLon, lon)
              maxLon = Math.max(maxLon, lon)
              minLat = Math.min(minLat, lat)
              maxLat = Math.max(maxLat, lat)
            }
          }
        }
      }

      if (
        minLon !== Infinity &&
        maxLon !== -Infinity &&
        minLat !== Infinity &&
        maxLat !== -Infinity &&
        minLon < maxLon &&
        minLat < maxLat
      ) {
        polygons.push({
          id: (record.id as string | undefined) ?? `${fallbackId}-polygon-${idx}`,
          bbox: [minLon, minLat, maxLon, maxLat],
          geometry: {
            type: 'MultiPolygon',
            coordinates: coords as number[][][][],
          },
          label: (record.location as string | undefined) ?? record.geocode?.result?.formatted_address ?? undefined,
          description: (record.description as string | undefined) ?? (record.original_text as string | undefined) ?? undefined,
          group,
        })
      }
      return
    }

    // Handle Polygon: [[[lon, lat], ...]] or bbox [west, south, east, north]
    let minLon = Infinity
    let maxLon = -Infinity
    let minLat = Infinity
    let maxLat = -Infinity
    
    if (Array.isArray(coords)) {
      // Check if it's bbox format: [west, south, east, north]
      if (coords.length === 4 && typeof coords[0] === 'number') {
        const west = toNumber(coords[0])
        const south = toNumber(coords[1])
        const east = toNumber(coords[2])
        const north = toNumber(coords[3])
        if (
          west !== null &&
          south !== null &&
          east !== null &&
          north !== null &&
          west < east &&
          south < north
        ) {
          polygons.push({
            id: (record.id as string | undefined) ?? `${fallbackId}-polygon-${idx}`,
            bbox: [west, south, east, north],
            label: (record.location as string | undefined) ?? record.geocode?.result?.formatted_address ?? undefined,
            description: (record.description as string | undefined) ?? (record.original_text as string | undefined) ?? undefined,
            group,
          })
        }
        return
      }
      
      // Full GeoJSON Polygon format: [[[lon, lat], ...]]
      if (Array.isArray(coords[0]) && Array.isArray(coords[0][0])) {
        const ring = coords[0] as number[][]
        for (const coord of ring) {
          if (Array.isArray(coord) && coord.length >= 2) {
            const lon = toNumber(coord[0])
            const lat = toNumber(coord[1])
            if (lon !== null && lat !== null) {
              minLon = Math.min(minLon, lon)
              maxLon = Math.max(maxLon, lon)
              minLat = Math.min(minLat, lat)
              maxLat = Math.max(maxLat, lat)
            }
          }
        }
        
        if (
          minLon !== Infinity &&
          maxLon !== -Infinity &&
          minLat !== Infinity &&
          maxLat !== -Infinity &&
          minLon < maxLon &&
          minLat < maxLat
        ) {
          polygons.push({
            id: (record.id as string | undefined) ?? `${fallbackId}-polygon-${idx}`,
            bbox: [minLon, minLat, maxLon, maxLat],
            geometry: {
              type: 'Polygon',
              coordinates: coords as number[][][],
            },
            label: (record.location as string | undefined) ?? record.geocode?.result?.formatted_address ?? undefined,
            description: (record.description as string | undefined) ?? (record.original_text as string | undefined) ?? undefined,
            group,
          })
        }
      }
    }
  }

  function addPoint(
    entry: unknown,
    fallbackId: string,
    idx: number,
    group: string,
    points: Array<{ id: string; coordinates: [number, number]; label?: string; description?: string; group?: string }>,
  ): void {
    if (!entry || typeof entry !== 'object') return
    const record = entry as Record<string, any>
    const geometry = record?.geocode?.result?.geometry
    if (!geometry || geometry.type !== 'Point') return

    const coords = geometry.coordinates
    if (!Array.isArray(coords) || coords.length !== 2) return

    const lon = toNumber(coords[0])
    const lat = toNumber(coords[1])
    if (lon === null || lat === null) return

    points.push({
      id: (record.id as string | undefined) ?? `${fallbackId}-point-${idx}`,
      coordinates: [lon, lat],
      label: (record.location as string | undefined) ?? record.geocode?.result?.formatted_address ?? undefined,
      description: (record.description as string | undefined) ?? (record.original_text as string | undefined) ?? undefined,
      group,
    })
  }

  const polygons: MapBoundingBoxFeature[] = []
  const points: MapPointFeature[] = []

  // Collect polygons from area groups
  const areaGroups = places.areas as Record<string, unknown[] | undefined> | undefined
  if (areaGroups && typeof areaGroups === 'object') {
    Object.entries(areaGroups).forEach(([groupName, entries]) => {
      if (!Array.isArray(entries)) return
      const displayGroup = groupName || 'areas'
      entries.forEach((entry: unknown, idx: number) => {
        const fallbackId = `${nodeId}-${groupName}`
        addPolygon(entry, fallbackId, idx, displayGroup, polygons)
        addPoint(entry, fallbackId, idx, displayGroup, points)
      })
    })
  }

  // Collect point results
  if (Array.isArray(places.points)) {
    places.points.forEach((entry: unknown, idx: number) =>
      addPoint(entry, `${nodeId}-point`, idx, 'points', points),
    )
  }

  // Some geocode nodes may emit point-like data in "other" buckets
  if (Array.isArray(places.other)) {
    places.other.forEach((entry: unknown, idx: number) =>
      addPoint(entry, `${nodeId}-other`, idx, 'other', points),
    )
  }

  if (polygons.length === 0 && points.length === 0) {
    return null
  }

  const displayNodeLabel =
    nodeLabel !== nodeId ? nodeLabel.replace(/\s*\(n\d+\)\s*$/, '') : null

  // Visualization component
  const GeocodeVisualization: React.FC<VisualizationProps> = ({ data }) => {
    if (!data) return null

    function pointsToGeoJSON(features: MapPointFeature[]) {
      return {
        type: 'FeatureCollection' as const,
        features: features.map((p) => ({
          type: 'Feature' as const,
          properties: {
            id: p.id,
            label: p.label ?? '',
            description: p.description ?? '',
            group: p.group ?? 'points',
          },
          geometry: { type: 'Point' as const, coordinates: p.coordinates },
        })),
      }
    }

    function polygonsToGeoJSON(features: MapBoundingBoxFeature[]) {
      const ringFromBbox = (bbox: [number, number, number, number]) => {
        const [w, s, e, n] = bbox
        return [
          [w, s],
          [e, s],
          [e, n],
          [w, n],
          [w, s],
        ] as [number, number][]
      }
      return {
        type: 'FeatureCollection' as const,
        features: features.map((p) => ({
          type: 'Feature' as const,
          properties: {
            id: p.id,
            label: p.label ?? '',
            description: p.description ?? '',
            group: p.group ?? 'areas',
          },
          geometry: (p.geometry
            ? p.geometry
            : { type: 'Polygon' as const, coordinates: [ringFromBbox(p.bbox)] }) as any,
        })),
      }
    }

    const layers = useMemo(() => {
      return layersFromFeatures([
        ...data.points.map((p) => ({ group: p.group ?? 'points' })),
        ...data.polygons.map((p) => ({ group: p.group ?? 'areas' })),
      ])
    }, [data.points, data.polygons])

    const [visibility, setVisibility] = useState(() => defaultVisibility(layers))
    useEffect(() => {
      setVisibility((prev) => {
        const next = { ...prev }
        for (const layer of layers) {
          if (!(layer.id in next)) next[layer.id] = true
        }
        return next
      })
    }, [layers])

    const filteredPoints = useMemo(() => {
      return data.points.filter((p) => visibility[p.group ?? 'points'] ?? true)
    }, [data.points, visibility])

    const filteredPolygons = useMemo(() => {
      return data.polygons.filter((p) => visibility[p.group ?? 'areas'] ?? true)
    }, [data.polygons, visibility])

    return (
      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-3 space-y-0">
          <CardTitle className="flex items-baseline gap-3">
            <span>Locations</span>
            {displayNodeLabel && (
              <span className="text-sm font-normal text-muted-foreground">{displayNodeLabel}</span>
            )}
          </CardTitle>

          <LayerFilterPopover
            layers={layers}
            visibility={visibility}
            onChange={setVisibility}
            buttonLabel="Layers"
          />
        </CardHeader>
        <CardContent>
          <LeafletMap
            points={pointsToGeoJSON(filteredPoints) as any}
            polygons={polygonsToGeoJSON(filteredPolygons) as any}
          />
        </CardContent>
      </Card>
    )
  }

  return {
    id: `${nodeId}-map`,
    nodeId,
    title: 'Locations',
    description: nodeLabel !== nodeId ? nodeLabel : undefined,
    component: GeocodeVisualization,
    requiresMapboxToken: false,
    data: {
      points,
      polygons,
    },
  }
}

