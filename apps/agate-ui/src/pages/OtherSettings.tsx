import { useCallback, useEffect, useState } from 'react'
import {
  CONTINENTAL_US_MAP_CENTER,
  CONTINENTAL_US_MAP_ZOOM,
  LeafletMap,
} from '@backfield/ui'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { AlertCircle } from 'lucide-react'
import { useAppMessage } from '@/components/AppMessageProvider'
import { useAuth } from '@/lib/auth'
import {
  getOrganizationSettings,
  patchOrganizationSettings,
  type MapDefaultViewport,
} from '@/lib/core-api'

export default function OtherSettings() {
  const { organizationId } = useAuth()
  const { showError, showMessage } = useAppMessage()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [savedViewport, setSavedViewport] = useState<MapDefaultViewport | null>(null)
  const [draftViewport, setDraftViewport] = useState<MapDefaultViewport>({
    lat: CONTINENTAL_US_MAP_CENTER[0],
    lng: CONTINENTAL_US_MAP_CENTER[1],
    zoom: CONTINENTAL_US_MAP_ZOOM,
  })
  const [mapKey, setMapKey] = useState(0)

  const reload = useCallback(async () => {
    if (organizationId == null) return
    const settings = await getOrganizationSettings(organizationId)
    const viewport = settings.map_default_viewport
    setSavedViewport(viewport)
    setDraftViewport(
      viewport ?? {
        lat: CONTINENTAL_US_MAP_CENTER[0],
        lng: CONTINENTAL_US_MAP_CENTER[1],
        zoom: CONTINENTAL_US_MAP_ZOOM,
      },
    )
    setMapKey((k) => k + 1)
  }, [organizationId])

  useEffect(() => {
    if (organizationId == null) {
      setLoading(false)
      return
    }
    let cancelled = false
    ;(async () => {
      try {
        setLoading(true)
        setError(null)
        await reload()
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : 'Could not load settings')
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [organizationId, reload])

  const isDirty = (() => {
    if (savedViewport == null) {
      return (
        Math.abs(draftViewport.lat - CONTINENTAL_US_MAP_CENTER[0]) > 1e-6 ||
        Math.abs(draftViewport.lng - CONTINENTAL_US_MAP_CENTER[1]) > 1e-6 ||
        Math.abs(draftViewport.zoom - CONTINENTAL_US_MAP_ZOOM) > 1e-6
      )
    }
    return (
      Math.abs(draftViewport.lat - savedViewport.lat) > 1e-6 ||
      Math.abs(draftViewport.lng - savedViewport.lng) > 1e-6 ||
      Math.abs(draftViewport.zoom - savedViewport.zoom) > 1e-6
    )
  })()

  const handleSave = async () => {
    if (organizationId == null) return
    try {
      setSaving(true)
      const next = await patchOrganizationSettings(organizationId, {
        map_default_viewport: draftViewport,
      })
      setSavedViewport(next.map_default_viewport)
      showMessage('Default map view saved.', { title: 'Done' })
    } catch (e) {
      showError(e instanceof Error ? e.message : 'Could not save settings.')
    } finally {
      setSaving(false)
    }
  }

  const handleClear = async () => {
    if (organizationId == null) return
    try {
      setSaving(true)
      await patchOrganizationSettings(organizationId, { map_default_viewport: null })
      setSavedViewport(null)
      setDraftViewport({
        lat: CONTINENTAL_US_MAP_CENTER[0],
        lng: CONTINENTAL_US_MAP_CENTER[1],
        zoom: CONTINENTAL_US_MAP_ZOOM,
      })
      setMapKey((k) => k + 1)
      showMessage('Default map view cleared.', { title: 'Done' })
    } catch (e) {
      showError(e instanceof Error ? e.message : 'Could not clear settings.')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <p className="text-sm text-muted-foreground">Loading…</p>
  }

  return (
    <div className="space-y-6 max-w-3xl">
      {error ? (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Default map view</CardTitle>
          <CardDescription>
            Pan and zoom to the area your organization usually works in. Empty maps use this view
            when there is nothing else to show.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="h-[420px] w-full overflow-hidden rounded-md border border-border">
            <LeafletMap
              key={mapKey}
              fillHeight
              interactiveWhenEmpty
              geocoder
              fitToData={false}
              initialCenter={[draftViewport.lat, draftViewport.lng]}
              initialZoom={draftViewport.zoom}
              onViewportChange={(v) => {
                setDraftViewport({
                  lat: v.center[0],
                  lng: v.center[1],
                  zoom: v.zoom,
                })
              }}
            />
          </div>
          <p className="text-xs text-muted-foreground tabular-nums">
            Center {draftViewport.lat.toFixed(4)}, {draftViewport.lng.toFixed(4)} · Zoom{' '}
            {draftViewport.zoom.toFixed(1)}
            {savedViewport == null ? ' · Using the shared continental default until you save' : null}
          </p>
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              onClick={() => void handleSave()}
              disabled={saving || (!isDirty && savedViewport != null)}
            >
              {saving ? 'Saving…' : 'Save'}
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={() => void handleClear()}
              disabled={saving || savedViewport == null}
            >
              Clear default
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
