import { useEffect, useMemo, useRef, useId, useState } from 'react'
import mapboxgl from 'mapbox-gl'
import 'mapbox-gl/dist/mapbox-gl.css'

import type { MapBoundingBoxFeature, MapPointFeature } from '@/lib/visualizations'

type MapboxMapProps = {
  accessToken: string
  points: MapPointFeature[]
  polygons: MapBoundingBoxFeature[]
  height?: number
}

const DEFAULT_CENTER: [number, number] = [-98.5795, 39.8283] // continental US
const POINT_FLY_ZOOM = 13

type LegendGroup = {
  id: string
  type: 'polygon' | 'point'
  label: string
}

function createPolygonCoordinates([west, south, east, north]: [
  number,
  number,
  number,
  number,
]): number[][] {
  return [
    [west, south],
    [east, south],
    [east, north],
    [west, north],
    [west, south],
  ]
}

function getBounds(points: MapPointFeature[], polygons: MapBoundingBoxFeature[]) {
  const bounds: any = new (mapboxgl as any).LngLatBounds()
  let hasBounds = false

  points.forEach((point) => {
    bounds.extend(point.coordinates)
    hasBounds = true
  })

  polygons.forEach((polygon) => {
    // If full geometry is available, extract bounds from it
    if (polygon.geometry) {
      const geom = polygon.geometry
      if (geom.type === 'Polygon' && Array.isArray(geom.coordinates) && geom.coordinates.length > 0) {
        // Extract bounds from Polygon exterior ring
        const exteriorRing = geom.coordinates[0]
        if (Array.isArray(exteriorRing)) {
          exteriorRing.forEach((coord: number[]) => {
            if (Array.isArray(coord) && coord.length >= 2) {
              bounds.extend([coord[0], coord[1]])
            }
          })
          hasBounds = true
        }
      } else if (geom.type === 'MultiPolygon' && Array.isArray(geom.coordinates)) {
        // Extract bounds from all polygons in MultiPolygon
        geom.coordinates.forEach((polygonCoords: number[][][]) => {
          if (Array.isArray(polygonCoords) && polygonCoords.length > 0) {
            const exteriorRing = polygonCoords[0]
            if (Array.isArray(exteriorRing)) {
              exteriorRing.forEach((coord: number[]) => {
                if (Array.isArray(coord) && coord.length >= 2) {
                  bounds.extend([coord[0], coord[1]])
                }
              })
            }
          }
        })
        hasBounds = true
      }
    } else {
      // Fallback to bbox
    const [west, south, east, north] = polygon.bbox
    bounds.extend([west, south])
    bounds.extend([east, north])
    hasBounds = true
    }
  })

  return hasBounds ? bounds : null
}

export default function MapboxMap({ accessToken, points, polygons, height = 420 }: MapboxMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const mapRef = useRef<any>(null)
  const popupRef = useRef<any>(null)
  const mapId = useId()
  const [visibleGroups, setVisibleGroups] = useState<Record<string, boolean>>({})
  const [selectedFeatureId, setSelectedFeatureId] = useState<string | null>(null)

  const pointData = useMemo(() => {
    return {
      type: 'FeatureCollection' as const,
      features: points.map((point) => ({
        type: 'Feature' as const,
        properties: {
          id: point.id,
          label: point.label ?? '',
          description: point.description ?? '',
          group: point.group ?? 'points',
        },
        geometry: {
          type: 'Point' as const,
          coordinates: point.coordinates,
        },
      })),
    }
  }, [points])

  const polygonData = useMemo(() => {
    return {
      type: 'FeatureCollection' as const,
      features: polygons.map((polygon) => {
        // Use full geometry if available, otherwise create from bbox
        let geometry: { type: 'Polygon' | 'MultiPolygon'; coordinates: any }
        if (polygon.geometry) {
          geometry = polygon.geometry as { type: 'Polygon' | 'MultiPolygon'; coordinates: any }
        } else {
          geometry = {
            type: 'Polygon' as const,
            coordinates: [createPolygonCoordinates(polygon.bbox)],
          }
        }
        
        return {
        type: 'Feature' as const,
        properties: {
          id: polygon.id,
          label: polygon.label ?? '',
          description: polygon.description ?? '',
          group: polygon.group ?? 'areas',
        },
          geometry,
        }
      }),
    }
  }, [polygons])

  useEffect(() => {
    if (!containerRef.current) return
    if (mapRef.current) return
    if (!accessToken) return

    mapboxgl.accessToken = accessToken

    const map = new mapboxgl.Map({
      container: containerRef.current,
      style: 'mapbox://styles/mapbox/streets-v12',
      center: DEFAULT_CENTER,
      zoom: 3,
    })

    map.addControl(new mapboxgl.NavigationControl(), 'top-right')
    mapRef.current = map

    const polygonSourceId = `${mapId}-polygon-source`
    const pointSourceId = `${mapId}-point-source`
    const polygonFillLayerId = `${polygonSourceId}-fill`
    const polygonOutlineLayerId = `${polygonSourceId}-outline`
    const pointLayerId = `${pointSourceId}-circle`

    const updateSources = () => {
      if (!map.getSource(polygonSourceId)) {
        map.addSource(polygonSourceId, {
          type: 'geojson',
          data: polygonData,
        })
        map.addLayer({
          id: `${polygonSourceId}-fill`,
          type: 'fill',
          source: polygonSourceId,
          paint: {
            'fill-color': '#3b82f6',
            'fill-opacity': 0.2,
          },
        })
        map.addLayer({
          id: polygonOutlineLayerId,
          type: 'line',
          source: polygonSourceId,
          paint: {
            'line-color': '#1d4ed8',
            'line-width': 2,
          },
        })
      }

      if (!map.getSource(pointSourceId)) {
        map.addSource(pointSourceId, {
          type: 'geojson',
          data: pointData,
        })
        map.addLayer({
          id: `${pointSourceId}-circle`,
          type: 'circle',
          source: pointSourceId,
          paint: {
            'circle-radius': 6,
            'circle-color': '#ef4444',
            'circle-stroke-width': 1.5,
            'circle-stroke-color': '#ffffff',
          },
        })
      }
    }

    const updateData = () => {
      const polygonSource = map.getSource(polygonSourceId) as any
      if (polygonSource) {
        polygonSource.setData(polygonData)
      }

      const pointSource = map.getSource(pointSourceId) as any
      if (pointSource) {
        pointSource.setData(pointData)
      }

      const bounds = getBounds(points, polygons)
      if (bounds) {
        map.fitBounds(bounds, { padding: 48, maxZoom: 12, duration: 0 })
      } else {
        map.setCenter(DEFAULT_CENTER)
        map.setZoom(2.5)
      }
    }

    if (map.isStyleLoaded()) {
      updateSources()
      updateData()
    } else {
      map.on('load', () => {
        updateSources()
        updateData()
      })
    }

    const showPopup = (feature: any, lngLat: [number, number]) => {
      const properties = feature.properties ?? {}
      const title = properties.label || properties.id || 'Location'
      const description = properties.description

      if (!popupRef.current) {
        popupRef.current = new mapboxgl.Popup({
          closeButton: true,
          closeOnClick: true,
          className: 'agate-map-popup',
        })
      }

      const content = document.createElement('div')
      content.className = 'text-sm'
      content.innerHTML = `
        <strong>${title}</strong>
        ${description ? `<div class="mt-1 text-xs text-muted-foreground">${description}</div>` : ''}
      `

      popupRef.current
        .setLngLat(lngLat)
        .setDOMContent(content)
        .addTo(map)
    }

    map.on('click', pointLayerId, (event: any) => {
      const feature = event.features?.[0]
      if (!feature) return
      setSelectedFeatureId(feature.properties?.id ?? null)
      showPopup(feature, event.lngLat.toArray() as [number, number])
    })
    map.on('mouseenter', pointLayerId, () => {
      map.getCanvas().style.cursor = 'pointer'
    })
    map.on('mouseleave', pointLayerId, () => {
      map.getCanvas().style.cursor = ''
    })

    map.on('click', polygonFillLayerId, (event: any) => {
      const feature = event.features?.[0]
      if (!feature) return
      setSelectedFeatureId(feature.properties?.id ?? null)
      showPopup(feature, event.lngLat.toArray() as [number, number])
    })
    map.on('mouseenter', polygonFillLayerId, () => {
      map.getCanvas().style.cursor = 'pointer'
    })
    map.on('mouseleave', polygonFillLayerId, () => {
      map.getCanvas().style.cursor = ''
    })

    return () => {
      if (popupRef.current) {
        popupRef.current.remove()
        popupRef.current = null
      }
      map.remove()
      mapRef.current = null
    }
  }, [accessToken, mapId, pointData, polygonData, points, polygons])

  // Update data when points/polygons change after initial load
  useEffect(() => {
    const map = mapRef.current
    if (!map) return

    const polygonSourceId = `${mapId}-polygon-source`
    const pointSourceId = `${mapId}-point-source`

    const updateData = () => {
      const polygonSource = map.getSource(polygonSourceId) as any
      if (polygonSource) {
        polygonSource.setData(polygonData)
      }

      const pointSource = map.getSource(pointSourceId) as any
      if (pointSource) {
        pointSource.setData(pointData)
      }

      const bounds = getBounds(points, polygons)
      if (bounds) {
        map.fitBounds(bounds, { padding: 48, maxZoom: 12, duration: 0 })
      }
    }

    if (map.isStyleLoaded()) {
      updateData()
    } else {
      map.once('load', updateData)
    }
  }, [mapId, pointData, polygonData, points, polygons])

  const legendGroups: LegendGroup[] = useMemo(() => {
    const entries: LegendGroup[] = []
    const seen = new Set<string>()

    polygons.forEach((polygon) => {
      const group = polygon.group ?? 'areas'
      if (!seen.has(group)) {
        seen.add(group)
        entries.push({ id: group, type: 'polygon', label: group })
      }
    })

    points.forEach((point) => {
      const group = point.group ?? 'points'
      if (!seen.has(group)) {
        seen.add(group)
        entries.push({ id: group, type: 'point', label: group })
      }
    })

    return entries
  }, [points, polygons])

  useEffect(() => {
    if (legendGroups.length === 0) return
    setVisibleGroups((prev) => {
      const updated: Record<string, boolean> = { ...prev }
      legendGroups.forEach((group) => {
        if (!(group.id in updated)) {
          updated[group.id] = true
        }
      })
      return updated
    })
  }, [legendGroups])

  useEffect(() => {
    const map = mapRef.current
    if (!map) return

    const polygonSourceId = `${mapId}-polygon-source`
    const pointSourceId = `${mapId}-point-source`
    const polygonFillLayerId = `${polygonSourceId}-fill`
    const polygonOutlineLayerId = `${polygonSourceId}-outline`
    const pointLayerId = `${pointSourceId}-circle`

    const activeGroups = Object.entries(visibleGroups)
      .filter(([, visible]) => visible)
      .map(([group]) => group)

    const filterExpression =
      activeGroups.length === 0
        ? (['==', ['get', 'group'], '__none__'] as any)
        : (['in', ['get', 'group'], ['literal', activeGroups]] as any)

    if (map.getLayer(polygonFillLayerId)) {
      map.setFilter(polygonFillLayerId, filterExpression)
    }
    if (map.getLayer(polygonOutlineLayerId)) {
      map.setFilter(polygonOutlineLayerId, filterExpression)
    }
    if (map.getLayer(pointLayerId)) {
      map.setFilter(pointLayerId, filterExpression)
    }
  }, [mapId, visibleGroups])

  const handleToggle = (groupId: string) => {
    setVisibleGroups((prev) => ({
      ...prev,
      [groupId]: !prev[groupId],
    }))
  }

  useEffect(() => {
    const map = mapRef.current
    if (!map) return

    const polygonSourceId = `${mapId}-polygon-source`
    const pointSourceId = `${mapId}-point-source`
    const polygonFillLayerId = `${polygonSourceId}-fill`
    const polygonOutlineLayerId = `${polygonSourceId}-outline`
    const pointLayerId = `${pointSourceId}-circle`

    const activeGroups = Object.entries(visibleGroups)
      .filter(([, visible]) => visible)
      .map(([group]) => group)

    const baseFilter =
      activeGroups.length === 0
        ? (['==', ['get', 'group'], '__none__'] as any)
        : (['in', ['get', 'group'], ['literal', activeGroups]] as any)

    const highlightMatch = ['==', ['get', 'id'], selectedFeatureId] as any

    if (map.getLayer(polygonFillLayerId)) {
      map.setFilter(polygonFillLayerId, baseFilter)
      map.setPaintProperty(polygonFillLayerId, 'fill-opacity', [
        'case',
        highlightMatch,
        0.35,
        0.2,
      ])
    }
    if (map.getLayer(polygonOutlineLayerId)) {
      map.setFilter(polygonOutlineLayerId, baseFilter)
      map.setPaintProperty(polygonOutlineLayerId, 'line-width', [
        'case',
        highlightMatch,
        4,
        2,
      ])
    }
    if (map.getLayer(pointLayerId)) {
      map.setFilter(pointLayerId, baseFilter)
      map.setPaintProperty(pointLayerId, 'circle-radius', [
        'case',
        highlightMatch,
        8,
        6,
      ])
    }
  }, [mapId, visibleGroups, selectedFeatureId])

  const flyToFeature = (featureId: string, type: 'Point' | 'Polygon') => {
    const map = mapRef.current
    if (!map) return

    const polygonSource = map.getSource(`${mapId}-polygon-source`) as any
    const pointSource = map.getSource(`${mapId}-point-source`) as any

    if (type === 'Point' && pointSource) {
      const data = pointSource._data
      const feature = data.features.find((f: any) => f.properties?.id === featureId)
      if (feature) {
        const target = feature.geometry.coordinates as [number, number]
        const maxZoom = typeof map.getMaxZoom === 'function' ? map.getMaxZoom() : POINT_FLY_ZOOM
        map.flyTo({ center: target, zoom: Math.min(POINT_FLY_ZOOM, maxZoom ?? POINT_FLY_ZOOM), duration: 500 })
      }
    } else if (type === 'Polygon' && polygonSource) {
      const data = polygonSource._data
      const feature = data.features.find((f: any) => f.properties?.id === featureId)
      if (feature) {
        const coords = feature.geometry.coordinates?.[0] as [number, number][] | undefined
        if (coords && coords.length > 0) {
          const bounds = new (mapboxgl as any).LngLatBounds(coords[0], coords[0])
          coords.forEach((coord) => bounds.extend(coord))
          map.fitBounds(bounds, { padding: 48, duration: 500, maxZoom: 14 })
        }
      }
    }
  }

  const handleRowClick = (featureId: string, type: 'Point' | 'Polygon') => {
    setSelectedFeatureId((current) => (current === featureId ? null : featureId))
    flyToFeature(featureId, type)
  }

  if (points.length === 0 && polygons.length === 0) {
    return (
      <div className="rounded-md border border-dashed border-muted h-[180px] flex items-center justify-center text-sm text-muted-foreground">
        This node did not produce any geocoded features to display.
      </div>
    )
  }

  const featuresForList = useMemo(() => {
    const polygonEntries = polygons.map((polygon) => ({
      id: polygon.id,
      type: 'Polygon' as const,
      label: polygon.label ?? polygon.id,
      description: polygon.description ?? '',
      bbox: polygon.bbox,
    }))

    const pointEntries = points.map((point) => ({
      id: point.id,
      type: 'Point' as const,
      label: point.label ?? point.id,
      description: point.description ?? '',
      coordinates: point.coordinates,
    }))

    return [...polygonEntries, ...pointEntries]
  }, [points, polygons])

  const formatCoordinates = (coords: [number, number] | [number, number, number, number]) => {
    if (coords.length === 2) {
      const [lon, lat] = coords
      return `${lat.toFixed(5)}, ${lon.toFixed(5)}`
    }
    const [west, south, east, north] = coords
    return `${south.toFixed(5)}, ${west.toFixed(5)} — ${north.toFixed(5)}, ${east.toFixed(5)}`
  }

  return (
    <div className="space-y-3">
      {legendGroups.length > 0 && (
        <div className="flex flex-wrap gap-2 text-sm">
          {legendGroups.map((group) => {
            const colorClass =
              group.type === 'polygon'
                ? 'bg-blue-100 text-blue-800 border border-blue-200'
                : 'bg-red-100 text-red-800 border border-red-200'
            return (
              <label
                key={group.id}
                className={`inline-flex items-center gap-2 px-3 py-1 rounded-full cursor-pointer select-none ${colorClass}`}
              >
                <input
                  type="checkbox"
                  checked={visibleGroups[group.id] ?? true}
                  onChange={() => handleToggle(group.id)}
                  className="h-4 w-4"
                />
                <span className="capitalize">{group.label}</span>
              </label>
            )
          })}
        </div>
      )}

      <div className="flex flex-col gap-4 md:flex-row">
        <div
          ref={containerRef}
          className="rounded-md overflow-hidden border border-border md:w-1/2 w-full"
          style={{ height }}
        />

        <div className="md:w-1/2 w-full rounded-md border border-border bg-card">
          <div className="max-h-[420px] overflow-y-auto divide-y divide-border">
            {featuresForList.map((feature) => (
              <button
                key={feature.id}
                type="button"
                onClick={() => handleRowClick(feature.id, feature.type)}
                className={`w-full text-left p-4 space-y-1 transition-colors ${
                  selectedFeatureId === feature.id ? 'bg-primary/10' : 'hover:bg-muted'
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-medium">{feature.label}</span>
                  <span className="text-xs uppercase tracking-wide text-muted-foreground">
                    {feature.type}
                  </span>
                </div>
                <div className="text-xs text-muted-foreground font-mono">
                  {feature.type === 'Point'
                    ? formatCoordinates((feature as any).coordinates)
                    : formatCoordinates((feature as any).bbox)}
                </div>
                {feature.description && (
                  <div className="text-sm text-muted-foreground">{feature.description}</div>
                )}
              </button>
            ))}
            {featuresForList.length === 0 && (
              <div className="p-4 text-sm text-muted-foreground">
                No geocoded features available.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

