import { useEffect, useState } from "react"
import {
  CONTINENTAL_US_MAP_CENTER,
  CONTINENTAL_US_MAP_ZOOM,
} from "@backfield/ui"
import { useAuth } from "@/lib/auth"
import { getOrganizationSettings } from "@/lib/core-api"

export type OrgMapViewport = {
  center: [number, number]
  zoom: number
}

const FALLBACK: OrgMapViewport = {
  center: CONTINENTAL_US_MAP_CENTER,
  zoom: CONTINENTAL_US_MAP_ZOOM,
}

/** Tenant map fallback for empty Stylebook maps (geometry framing still wins). */
export function useOrgMapDefaultViewport(): OrgMapViewport {
  const { organizationId } = useAuth()
  const [viewport, setViewport] = useState<OrgMapViewport>(FALLBACK)

  useEffect(() => {
    if (organizationId == null) {
      setViewport(FALLBACK)
      return
    }
    let cancelled = false
    void getOrganizationSettings(organizationId)
      .then((settings) => {
        if (cancelled) return
        const v = settings.map_default_viewport
        if (v == null) {
          setViewport(FALLBACK)
          return
        }
        setViewport({ center: [v.lat, v.lng], zoom: v.zoom })
      })
      .catch(() => {
        if (!cancelled) setViewport(FALLBACK)
      })
    return () => {
      cancelled = true
    }
  }, [organizationId])

  return viewport
}
