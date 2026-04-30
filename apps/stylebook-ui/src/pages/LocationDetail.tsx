import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useNavigate, useParams, useSearchParams } from "react-router-dom"
import {
  deleteCanonicalLocation,
  getCanonicalLocation,
  getCanonicalLocationMentions,
  getLocation,
  listCanonicalLinkedSubstrates,
  patchCanonicalLocation,
  unlinkSubstrateFromCanonical,
  type CanonicalLocation,
  type LinkedMention,
  type LinkedSubstrateItem,
} from "@/lib/api"
import { placeExtractTypeLabel } from "@/lib/place-extract-type-label"
import { useAppMessage } from "@/components/AppMessageProvider"
import { CanonicalLinkModal } from "@/components/CanonicalLinkModal"
import { updateCanonicalLocationGeometry } from "@/lib/stylebook-api/locations"
import { cn } from "@/lib/utils"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import SimpleGeoJsonGeometry from "@/components/SimpleGeoJsonGeometry"
import LocationMetaTab from "@/components/LocationMetaTab"
import ConnectionsSection from "@/components/ConnectionsSection"
import { LeafletMap } from "@backfield/ui/LeafletMap"
import {
  boundsFromPolygonGeometry,
  isAxisAlignedRectanglePolygon,
  polygonFromAxisAlignedBounds,
} from "@backfield/ui/axisAlignedRectangle"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Info, Loader2, MousePointer, Square, Trash2 } from "lucide-react"
import { Alert, AlertDescription } from "@/components/ui/alert"

/** Continental US when adding the first geometry from an empty draft (matches LeafletMap defaults). */
const ADD_GEOMETRY_MAP_CENTER: [number, number] = [39.8283, -98.5795]
/** Match @backfield/ui LeafletMap continental US default framing. */
const ADD_GEOMETRY_MAP_ZOOM = 3

function mentionArticleDisplayTitle(m: LinkedMention): string {
  const trimmed = (m.article_headline ?? "").trim()
  if (trimmed.length > 0) return trimmed
  return `Article ${m.article_id}`
}

function mentionArticleHref(m: LinkedMention): string | null {
  const u = (m.article_url ?? "").trim()
  return u.length > 0 ? u : null
}

function mentionNatureDisplayLabel(raw: string | null | undefined): string {
  const s = (raw ?? "").trim().toLowerCase()
  if (!s) return "Unknown"
  return s.charAt(0).toUpperCase() + s.slice(1)
}

function mentionNatureBadgeClass(raw: string | null | undefined): string {
  const s = (raw ?? "").trim().toLowerCase()
  switch (s) {
    case "primary":
      return "border-primary/35 bg-primary/10 text-primary"
    case "secondary":
      return "border-muted-foreground/25 bg-muted text-muted-foreground"
    case "subject":
      return "border-violet-500/40 bg-violet-500/10 text-violet-900 dark:text-violet-200"
    case "context":
      return "border-sky-500/40 bg-sky-500/10 text-sky-900 dark:text-sky-100"
    case "person":
      return "border-amber-500/45 bg-amber-500/12 text-amber-950 dark:text-amber-100"
    default:
      return "border-border bg-background text-muted-foreground"
  }
}

type GeoJsonGeometry =
  | { type: "Point"; coordinates: [number, number] }
  | { type: "Polygon"; coordinates: [number, number][][] }
  | { type: "MultiPolygon"; coordinates: [number, number][][][] }

function isPointGeometry(geometry: Record<string, unknown> | null): geometry is {
  type: "Point"
  coordinates: [number, number]
} {
  if (!geometry || typeof geometry !== "object") return false
  const g = geometry as Record<string, unknown>
  if (g.type !== "Point") return false
  const c = g.coordinates
  return Array.isArray(c) && c.length === 2 && typeof c[0] === "number" && typeof c[1] === "number"
}

function isPolygonGeometry(geometry: Record<string, unknown> | null): geometry is {
  type: "Polygon"
  coordinates: number[][][]
} {
  if (!geometry || typeof geometry !== "object") return false
  const g = geometry as Record<string, unknown>
  if (g.type !== "Polygon") return false
  const c = g.coordinates
  return Array.isArray(c) && c.length > 0
}

function isMultiPolygonGeometry(geometry: Record<string, unknown> | null): boolean {
  if (!geometry || typeof geometry !== "object") return false
  const g = geometry as Record<string, unknown>
  return g.type === "MultiPolygon"
}

function axisAlignedRectangleDraft(geometry: Record<string, unknown> | null): boolean {
  if (!isPolygonGeometry(geometry)) return false
  return isAxisAlignedRectanglePolygon(geometry)
}

function geometryToFeatureCollections(
  geometry: Record<string, unknown> | null,
  opts?: { featureId?: string; label?: string; group?: string },
): { points: unknown; polygons: unknown } {
  if (!geometry || typeof geometry !== "object") {
    return {
      points: { type: "FeatureCollection", features: [] },
      polygons: { type: "FeatureCollection", features: [] },
    }
  }

  const featureId = opts?.featureId ?? "canonical"
  const label = opts?.label ?? "Canonical"
  const group = opts?.group ?? "canonical"

  const g = geometry as Partial<GeoJsonGeometry>
  const type = typeof g.type === "string" ? g.type : null

  if (type === "Point" && Array.isArray(g.coordinates) && g.coordinates.length === 2) {
    const coords = g.coordinates as [number, number]
    return {
      points: {
        type: "FeatureCollection",
        features: [
          {
            type: "Feature",
            properties: { id: featureId, label, group },
            geometry: { type: "Point", coordinates: coords },
          },
        ],
      },
      polygons: { type: "FeatureCollection", features: [] },
    }
  }

  if (
    (type === "Polygon" || type === "MultiPolygon") &&
    Array.isArray(g.coordinates) &&
    g.coordinates.length > 0
  ) {
    return {
      points: { type: "FeatureCollection", features: [] },
      polygons: {
        type: "FeatureCollection",
        features: [
          {
            type: "Feature",
            properties: { id: featureId, label, group },
            geometry: { type, coordinates: g.coordinates },
          },
        ],
      },
    }
  }

  return {
    points: { type: "FeatureCollection", features: [] },
    polygons: { type: "FeatureCollection", features: [] },
  }
}

export default function LocationDetail() {
  const { showError, showConfirm } = useAppMessage()
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [canonical, setCanonical] = useState<CanonicalLocation | null>(null)
  const [mentions, setMentions] = useState<LinkedMention[]>([])
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState(false)
  const [projectSlug, setProjectSlug] = useState("")
  const [label, setLabel] = useState("")
  const [locationType, setLocationType] = useState("")
  const [formattedAddress, setFormattedAddress] = useState("")
  const [geometry, setGeometry] = useState<Record<string, unknown> | null>(null)
  const [geometryEditing, setGeometryEditing] = useState(false)
  const [geometryDraft, setGeometryDraft] = useState<Record<string, unknown> | null>(null)
  const [geometrySaving, setGeometrySaving] = useState(false)
  const [geometryAddMode, setGeometryAddMode] = useState<"point" | "rectangle" | null>(null)
  const [rectanglePreview, setRectanglePreview] = useState<{
    southWest: { lat: number; lng: number }
    northEast: { lat: number; lng: number }
  } | null>(null)
  const [saving, setSaving] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [substrates, setSubstrates] = useState<LinkedSubstrateItem[]>([])
  const [substratesLoading, setSubstratesLoading] = useState(false)
  const [mentionsLoading, setMentionsLoading] = useState(false)
  const [moveSubstrateId, setMoveSubstrateId] = useState<number | null>(null)
  const [unlinkingId, setUnlinkingId] = useState<number | null>(null)
  const [substrateGeometryOpen, setSubstrateGeometryOpen] = useState(false)
  const [substrateGeometryLoading, setSubstrateGeometryLoading] = useState(false)
  const [substrateGeometrySubstrate, setSubstrateGeometrySubstrate] =
    useState<LinkedSubstrateItem | null>(null)
  const [substrateGeometryJson, setSubstrateGeometryJson] = useState<Record<string, unknown> | null>(
    null,
  )
  const [adoptingSubstrateGeometry, setAdoptingSubstrateGeometry] = useState(false)
  const prevMentionCountRef = useRef<number | null>(null)
  const prevSubstrateCountRef = useRef<number | null>(null)
  const lastCanonicalKeyRef = useRef<string>("")

  useEffect(() => {
    const key = `${projectSlug}:${id ?? ""}`
    if (key !== lastCanonicalKeyRef.current) {
      lastCanonicalKeyRef.current = key
      prevMentionCountRef.current = null
      prevSubstrateCountRef.current = null
    }
  }, [id, projectSlug])

  useEffect(() => {
    const slug = searchParams.get("project") || ""
    setProjectSlug(slug)
  }, [searchParams])

  const loadCanonical = async (canonicalId: string, slug: string, quiet = false) => {
    try {
      if (!quiet) setLoading(true)
      const row = await getCanonicalLocation(canonicalId, slug)
      setCanonical(row)
      setLabel(row.label)
      setLocationType(row.location_type ?? "")
      setFormattedAddress(row.formatted_address ?? "")
      setGeometry((row.geometry_json as Record<string, unknown> | undefined) ?? null)
      setGeometryDraft((row.geometry_json as Record<string, unknown> | undefined) ?? null)
    } catch (e) {
      console.error(e)
    } finally {
      if (!quiet) setLoading(false)
    }
  }

  useEffect(() => {
    if (!id || !projectSlug) return
    void loadCanonical(id, projectSlug)
  }, [id, projectSlug])

  const loadMentions = useCallback(async (canonicalId: string, slug: string, quiet = false) => {
    if (!quiet) setMentionsLoading(true)
    try {
      const m = await getCanonicalLocationMentions(canonicalId, slug, 500, 0)
      setMentions(m.mentions)
    } catch {
      setMentions([])
    } finally {
      if (!quiet) setMentionsLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!id || !projectSlug) return
    void loadMentions(id, projectSlug)
  }, [id, projectSlug, loadMentions])

  const loadSubstrates = useCallback(async (canonicalId: string, slug: string, quiet = false) => {
    if (!quiet) setSubstratesLoading(true)
    try {
      const r = await listCanonicalLinkedSubstrates(canonicalId, slug)
      setSubstrates(r.substrates)
    } catch {
      setSubstrates([])
    } finally {
      if (!quiet) setSubstratesLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!id || !projectSlug) return
    void loadSubstrates(id, projectSlug)
  }, [id, projectSlug, loadSubstrates])

  /** @param quiet When true, refresh substrates/mentions without the full-table loading state (avoids a flash after unlink / move). */
  const refreshCanonicalPage = useCallback(
    async (quiet = false) => {
      if (!id || !projectSlug) return
      await loadCanonical(id, projectSlug, true)
      await loadSubstrates(id, projectSlug, quiet)
      await loadMentions(id, projectSlug, quiet)
    },
    [id, projectSlug, loadCanonical, loadMentions, loadSubstrates],
  )

  const mentionsBySubstrateId = useMemo(() => {
    const map = new Map<number, LinkedMention[]>()
    for (const row of mentions) {
      const sid = row.substrate_location_id
      const bucket = map.get(sid) ?? []
      bucket.push(row)
      map.set(sid, bucket)
    }
    return map
  }, [mentions])

  const tableLoading = substratesLoading || mentionsLoading

  async function handleUnlinkSubstrate(sub: LinkedSubstrateItem) {
    if (!projectSlug) return
    setUnlinkingId(sub.id)
    try {
      await unlinkSubstrateFromCanonical(sub.id, projectSlug)
      await refreshCanonicalPage(true)
    } catch (e) {
      showError(e instanceof Error ? e.message : "Unlink failed")
    } finally {
      setUnlinkingId(null)
    }
  }

  const saveEdits = async () => {
    if (!canonical || !id || !projectSlug) return
    setSaving(true)
    try {
      const canonicalId = id
      const updated = await patchCanonicalLocation(canonicalId, projectSlug, {
        label: label.trim(),
        location_type: locationType.trim() === "" ? null : locationType.trim().toLowerCase(),
        formatted_address: formattedAddress.trim() === "" ? null : formattedAddress.trim(),
      })
      setCanonical(updated)
      setEditing(false)
      await loadCanonical(canonicalId, projectSlug)
      await loadSubstrates(canonicalId, projectSlug)
      await loadMentions(canonicalId, projectSlug)
    } catch (e) {
      console.error(e)
      showError(e instanceof Error ? e.message : "Save failed")
    } finally {
      setSaving(false)
    }
  }

  const saveGeometry = async () => {
    if (!canonical || !id || !projectSlug) return
    setGeometrySaving(true)
    try {
      const canonicalId = id
      await updateCanonicalLocationGeometry(canonicalId, projectSlug, geometryDraft)
      setGeometryEditing(false)
      setGeometryAddMode(null)
      setRectanglePreview(null)
      await loadCanonical(canonicalId, projectSlug, true)
    } catch (e) {
      console.error(e)
      const msg =
        e instanceof Error ? e.message : typeof e === "string" ? e : "Save geometry failed"
      showError(msg)
    } finally {
      setGeometrySaving(false)
    }
  }

  const onDelete = useCallback(async () => {
    if (!canonical || !id || !projectSlug) return
    setDeleting(true)
    try {
      await deleteCanonicalLocation(id, projectSlug)
      navigate(`/locations/canonical?project=${projectSlug}`)
    } catch (e) {
      showError(e instanceof Error ? e.message : "Delete failed")
    } finally {
      setDeleting(false)
      setDeleteOpen(false)
    }
  }, [canonical, id, navigate, projectSlug, showError])

  useEffect(() => {
    if (!id || !projectSlug) return
    if (mentionsLoading || substratesLoading) return

    const mentionCount = mentions.length
    const substrateCount = substrates.length

    const prevMentions = prevMentionCountRef.current
    const prevSubs = prevSubstrateCountRef.current

    // Establish baseline after first successful refresh for this canonical.
    if (prevMentions === null || prevSubs === null) {
      prevMentionCountRef.current = mentionCount
      prevSubstrateCountRef.current = substrateCount
      return
    }

    const mentionsCleared = prevMentions > 0 && mentionCount === 0
    const noLinkedSubstrates = substrateCount === 0

    if (mentionsCleared && noLinkedSubstrates) {
      void (async () => {
        const ok = await showConfirm(
          "All mentions for this canonical have been removed. Would you like to delete it?",
          {
            title: "Delete canonical?",
            confirmLabel: "Delete canonical",
            cancelLabel: "Keep",
            destructive: true,
          },
        )
        if (ok) {
          await onDelete()
        }
        prevMentionCountRef.current = mentionCount
        prevSubstrateCountRef.current = substrateCount
      })()
      return
    }

    prevMentionCountRef.current = mentionCount
    prevSubstrateCountRef.current = substrateCount
  }, [
    id,
    projectSlug,
    mentions,
    mentionsLoading,
    substrates,
    substratesLoading,
    showConfirm,
    onDelete,
  ])

  const geometrySource = geometryEditing ? geometryDraft : geometry
  const geometryDraftIsMultiPolygon = geometryEditing && isMultiPolygonGeometry(geometryDraft)
  const allowGeometryMapEditing = geometryEditing && !geometryDraftIsMultiPolygon

  const leafletCollections = useMemo(() => {
    const base = geometryToFeatureCollections(geometrySource as any, {
      featureId: "canonical",
      label: "Canonical",
      group: "canonical",
    })

    const stripCanonicalPolygon = (polygons: any) => {
      const fc = polygons as any
      if (!fc || typeof fc !== "object" || fc.type !== "FeatureCollection" || !Array.isArray(fc.features)) return fc
      return {
        ...fc,
        features: fc.features.filter((f: any) => {
          const id = f?.properties?.id
          return id !== "canonical"
        }),
      }
    }

    const hideCanonicalPolygon =
      geometryEditing &&
      (geometryAddMode === "rectangle" || rectanglePreview != null || axisAlignedRectangleDraft(geometryDraft))

    return {
      points: base.points,
      polygons: hideCanonicalPolygon ? stripCanonicalPolygon(base.polygons) : base.polygons,
    }
  }, [geometryAddMode, geometryDraft, geometryEditing, geometrySource, rectanglePreview])

  const openSubstrateGeometry = useCallback(
    async (sub: LinkedSubstrateItem) => {
      if (!projectSlug) return
      setSubstrateGeometrySubstrate(sub)
      setSubstrateGeometryJson(null)
      setSubstrateGeometryOpen(true)
      setSubstrateGeometryLoading(true)
      try {
        const row = await getLocation(sub.id, projectSlug)
        const g = (row.geometry_json as Record<string, unknown> | undefined) ?? null
        setSubstrateGeometryJson(g)
      } catch (e) {
        showError(e instanceof Error ? e.message : "Could not load substrate geometry")
      } finally {
        setSubstrateGeometryLoading(false)
      }
    },
    [projectSlug, showError],
  )

  const handleAdoptSubstrateGeometry = useCallback(async () => {
    if (!canonical || !projectSlug || !substrateGeometrySubstrate) return
    if (!substrateGeometryJson || typeof substrateGeometryJson !== "object") return
    setAdoptingSubstrateGeometry(true)
    try {
      await updateCanonicalLocationGeometry(canonical.id, projectSlug, substrateGeometryJson)
      await loadCanonical(canonical.id, projectSlug, true)
      setSubstrateGeometryOpen(false)
    } catch (e) {
      showError(e instanceof Error ? e.message : "Could not adopt geometry")
    } finally {
      setAdoptingSubstrateGeometry(false)
    }
  }, [
    canonical,
    loadCanonical,
    projectSlug,
    showError,
    substrateGeometryJson,
    substrateGeometrySubstrate,
  ])

  const leafletInitialCenter = useMemo((): [number, number] | null => {
    const g = (geometryEditing ? geometryDraft : geometry) as Record<string, unknown> | null
    if (!g) return null
    if (isPointGeometry(g)) {
      const c = g.coordinates
      return [c[1], c[0]]
    }
    if (isPolygonGeometry(g)) {
      const b = boundsFromPolygonGeometry(g as any)
      if (!b) return null
      const lat = (b.south + b.north) / 2
      const lng = (b.west + b.east) / 2
      return [lat, lng]
    }
    if (isMultiPolygonGeometry(g)) {
      const coords = (g as any).coordinates?.[0]?.[0]?.[0]
      if (Array.isArray(coords) && coords.length >= 2 && typeof coords[0] === "number" && typeof coords[1] === "number") {
        return [coords[1], coords[0]]
      }
    }
    return null
  }, [geometry, geometryDraft, geometryEditing])

  if (loading || !canonical) {
    return (
      <div className="flex justify-center items-center py-16">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <div className="container mx-auto p-6 space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-3xl font-bold">{canonical.label}</h1>
        <div className="flex gap-2">
          {editing ? (
            <>
              <Button
                variant="outline"
                onClick={() => {
                  if (canonical) {
                    setLabel(canonical.label)
                    setLocationType(canonical.location_type ?? "")
                    setFormattedAddress(canonical.formatted_address ?? "")
                    const nextGeom =
                      (canonical.geometry_json as Record<string, unknown> | undefined) ?? null
                    setGeometry(nextGeom)
                    setGeometryDraft(nextGeom)
                  }
                  setEditing(false)
                }}
                disabled={saving}
              >
                Cancel
              </Button>
              <Button onClick={() => void saveEdits()} disabled={saving}>
                {saving ? "Saving…" : "Save"}
              </Button>
            </>
          ) : (
            <>
              <Button
                variant="outline"
                onClick={() => {
                  if (canonical) {
                    setLabel(canonical.label)
                    setLocationType(canonical.location_type ?? "")
                    setFormattedAddress(canonical.formatted_address ?? "")
                    const nextGeom =
                      (canonical.geometry_json as Record<string, unknown> | undefined) ?? null
                    setGeometry(nextGeom)
                    setGeometryDraft(nextGeom)
                  }
                  setEditing(true)
                }}
              >
                Edit
              </Button>
              <Button variant="destructive" size="icon" onClick={() => setDeleteOpen(true)}>
                <Trash2 className="h-4 w-4" />
              </Button>
            </>
          )}
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Details</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 max-w-xl">
          <div>
            <Label>Label</Label>
            {editing ? (
              <Input value={label} onChange={(e) => setLabel(e.target.value)} />
            ) : (
              <p className="text-sm mt-1.5">{canonical.label || "—"}</p>
            )}
          </div>
          <div>
            <Label>Location type</Label>
            {editing ? (
              <Input
                value={locationType}
                onChange={(e) => setLocationType(e.target.value)}
                placeholder="e.g. city, neighborhood"
              />
            ) : (
              <p className="text-sm mt-1.5">{canonical.location_type || "—"}</p>
            )}
          </div>
          <div>
            <Label>Formatted address</Label>
            {editing ? (
              <Input
                value={formattedAddress}
                onChange={(e) => setFormattedAddress(e.target.value)}
                placeholder="e.g. Chicago, IL, USA"
              />
            ) : (
              <p className="text-sm mt-1.5">{canonical.formatted_address || "—"}</p>
            )}
          </div>
        </CardContent>
      </Card>

      <Card
        className={cn(
          geometryEditing &&
            "border-2 border-foreground/80 bg-white shadow-sm transition-colors",
        )}
      >
        <CardHeader className="flex flex-row items-center justify-between gap-3 space-y-0">
          <div>
            <CardTitle className="flex items-center gap-2">
              <span>Geography</span>
              {geometryEditing ? (
                <Badge variant="secondary" className="font-normal">
                  Editing draft
                </Badge>
              ) : null}
            </CardTitle>
            <CardDescription>
              {geometryEditing
                ? geometryAddMode === "point"
                  ? "Click the map to place a point."
                  : geometryAddMode === "rectangle"
                    ? "Hold Shift and drag on the map to draw an axis-aligned rectangle."
                    : "Edit canonical geometry (draft) and save or cancel."
                : "View canonical geometry."}
            </CardDescription>
          </div>
          <div className="flex items-center gap-2">
            {geometryEditing ? (
              <>
                <Button
                  variant="outline"
                  onClick={() => {
                    setGeometryDraft(geometry)
                    setGeometryAddMode(null)
                    setRectanglePreview(null)
                    setGeometryEditing(false)
                  }}
                  disabled={geometrySaving}
                >
                  Cancel
                </Button>
                <Button onClick={() => void saveGeometry()} disabled={geometrySaving}>
                  {geometrySaving ? "Saving…" : "Save"}
                </Button>
              </>
            ) : (
              <Button
                variant="outline"
                onClick={() => {
                  setGeometryDraft(geometry)
                  setGeometryAddMode(null)
                  setRectanglePreview(null)
                  setGeometryEditing(true)
                }}
              >
                Edit geography
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          {geometryEditing && isMultiPolygonGeometry(geometryDraft) ? (
            <Alert>
              <Info className="h-4 w-4" />
              <AlertDescription>
                Editing is disabled for MultiPolygon geometries. These complex geometries contain multiple polygons and
                require specialized editing tools. You can delete the geometry, then add a point or rectangle replacement.
              </AlertDescription>
            </Alert>
          ) : null}

          {geometryEditing ? (
            <div className="flex flex-wrap gap-2">
              {!geometryDraft ? (
                <>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={geometryAddMode === "point" || geometrySaving}
                    onClick={() => {
                      setGeometryAddMode("point")
                      setRectanglePreview(null)
                    }}
                  >
                    <MousePointer className="h-4 w-4 mr-2" />
                    Add point
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={geometryAddMode === "rectangle" || geometrySaving}
                    onClick={() => {
                      setGeometryAddMode("rectangle")
                      setRectanglePreview(null)
                    }}
                  >
                    <Square className="h-4 w-4 mr-2" />
                    Add rectangle
                  </Button>
                </>
              ) : (
                <Button
                  type="button"
                  variant="destructive"
                  size="sm"
                  disabled={geometrySaving}
                  onClick={() => {
                    void (async () => {
                      const ok = await showConfirm("Delete this geometry?", {
                        title: "Delete geometry",
                        confirmLabel: "Delete",
                        destructive: true,
                      })
                      if (!ok) return
                      setGeometryDraft(null)
                      setGeometryAddMode(null)
                      setRectanglePreview(null)
                    })()
                  }}
                >
                  <Trash2 className="h-4 w-4 mr-2" />
                  Delete geometry
                </Button>
              )}
            </div>
          ) : null}

          <div
            className={cn(
              "rounded-md overflow-hidden",
              geometryEditing && "bg-white ring-1 ring-foreground/25 border border-foreground/30",
            )}
          >
            <LeafletMap
              points={leafletCollections.points as any}
              polygons={leafletCollections.polygons as any}
              geocoder={allowGeometryMapEditing}
              showPopups={false}
              // While editing, geometry updates constantly (drag/resize). Auto fitBounds would fight manual zoom.
              fitToData={!allowGeometryMapEditing}
              initialCenter={
                allowGeometryMapEditing &&
                !geometryDraft &&
                (geometryAddMode === "point" || geometryAddMode === "rectangle")
                  ? ADD_GEOMETRY_MAP_CENTER
                  : leafletInitialCenter
              }
              initialZoom={
                allowGeometryMapEditing &&
                !geometryDraft &&
                (geometryAddMode === "point" || geometryAddMode === "rectangle")
                  ? ADD_GEOMETRY_MAP_ZOOM
                  : null
              }
              interactiveWhenEmpty={
                allowGeometryMapEditing && geometryAddMode === "point" && !geometryDraft
              }
              tileUrl={
                allowGeometryMapEditing
                  ? "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
                  : undefined
              }
              tileAttribution={
                allowGeometryMapEditing
                  ? '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>'
                  : undefined
              }
              onMapClick={
                allowGeometryMapEditing &&
                geometryAddMode === "point" &&
                (!geometryDraft || isPointGeometry(geometryDraft))
                  ? ({ latlng }) => {
                      setGeometryDraft({ type: "Point", coordinates: [latlng.lng, latlng.lat] })
                      setGeometryAddMode(null)
                    }
                  : undefined
              }
              editablePoint={
                allowGeometryMapEditing &&
                isPointGeometry(geometryDraft) &&
                geometryAddMode !== "rectangle"
                  ? {
                      featureId: "canonical",
                      onChange: ({ lng, lat }) =>
                        setGeometryDraft({ type: "Point", coordinates: [lng, lat] }),
                    }
                  : null
              }
              rectanglePreview={allowGeometryMapEditing ? rectanglePreview : null}
              editableRectangle={
                allowGeometryMapEditing &&
                axisAlignedRectangleDraft(geometryDraft) &&
                geometryAddMode !== "rectangle" &&
                boundsFromPolygonGeometry(geometryDraft as any)
                  ? (() => {
                      const b = boundsFromPolygonGeometry(geometryDraft as any)!
                      return {
                        southWest: { lat: b.south, lng: b.west },
                        northEast: { lat: b.north, lng: b.east },
                        onChange: (next) => {
                          setGeometryDraft(
                            polygonFromAxisAlignedBounds({
                              west: next.southWest.lng,
                              south: next.southWest.lat,
                              east: next.northEast.lng,
                              north: next.northEast.lat,
                            }) as any,
                          )
                        },
                      }
                    })()
                  : null
              }
              rectangleDraw={
                allowGeometryMapEditing && geometryAddMode === "rectangle"
                  ? {
                      enabled: true,
                      onPreview: setRectanglePreview,
                      onCommit: (bounds) => {
                        setGeometryDraft(
                          polygonFromAxisAlignedBounds({
                            west: bounds.southWest.lng,
                            south: bounds.southWest.lat,
                            east: bounds.northEast.lng,
                            north: bounds.northEast.lat,
                          }) as any,
                        )
                        setRectanglePreview(null)
                        setGeometryAddMode(null)
                      },
                    }
                  : null
              }
            />
          </div>
          {geometryEditing && !geometryDraftIsMultiPolygon ? (
            <SimpleGeoJsonGeometry value={geometryDraft} onChange={setGeometryDraft} />
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Mentions</CardTitle>
          <CardDescription>
            Article mentions are grouped by place. Unlink or reassign places below.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {tableLoading ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground py-4">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading…
            </div>
          ) : substrates.length === 0 ? (
            <p className="text-sm text-muted-foreground">No linked substrate places.</p>
          ) : (
            <Table className="table-fixed w-full">
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[26%] min-w-[9rem]">Place / article</TableHead>
                  <TableHead className="w-[6.5rem] min-w-[5.5rem]">Nature</TableHead>
                  <TableHead className="w-[10rem]">Type / role</TableHead>
                  <TableHead>Quoted text</TableHead>
                  <TableHead className="w-[12rem] min-w-[12rem] text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {substrates.map((s) => {
                  const group = mentionsBySubstrateId.get(s.id) ?? []
                  return (
                    <Fragment key={`group-${s.id}`}>
                      <TableRow className="bg-muted/50 border-t">
                        <TableCell colSpan={4} className="align-top py-3">
                          <div className="flex items-center gap-2 min-w-0">
                            <div className="font-medium min-w-0 break-words">{s.name}</div>
                            <button
                              type="button"
                              className="text-xs text-primary hover:underline shrink-0"
                              onClick={() => void openSubstrateGeometry(s)}
                            >
                              View geometry
                            </button>
                          </div>
                          <div className="text-xs text-muted-foreground mt-0.5 break-words">
                            {(s.location_type || "").trim()
                              ? placeExtractTypeLabel(s.location_type)
                              : "—"}{" "}
                            <span className="text-muted-foreground/70">·</span>{" "}
                            {(s.formatted_address ?? "").trim() || "—"}
                          </div>
                        </TableCell>
                        <TableCell className="text-right align-top py-3 w-[12rem] min-w-[12rem]">
                          <div className="flex flex-wrap justify-end gap-2">
                            <Button
                              size="sm"
                              variant="outline"
                              className="shrink-0"
                              disabled={unlinkingId === s.id}
                              onClick={() => setMoveSubstrateId(s.id)}
                            >
                              Move…
                            </Button>
                            <Button
                              size="sm"
                              variant="secondary"
                              className="shrink-0"
                              disabled={unlinkingId === s.id}
                              onClick={() => void handleUnlinkSubstrate(s)}
                            >
                              {unlinkingId === s.id ? "Unlinking…" : "Unlink"}
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                      {group.length === 0 ? (
                        <TableRow>
                          <TableCell colSpan={5} className="pl-8 text-sm text-muted-foreground py-2">
                            No article mentions for this place.
                          </TableCell>
                        </TableRow>
                      ) : (
                        group.map((m) => {
                          const articleHref = mentionArticleHref(m)
                          const articleLabel = mentionArticleDisplayTitle(m)
                          return (
                          <TableRow key={m.mention_id} className="hover:bg-muted/30">
                            <TableCell className="pl-8 align-top min-w-0">
                              <div className="flex items-start gap-1 min-w-0">
                                <span
                                  className="text-muted-foreground select-none shrink-0 pt-0.5"
                                  aria-hidden
                                >
                                  ↳
                                </span>
                                <div className="min-w-0">
                                  {articleHref ? (
                                    <a
                                      href={articleHref}
                                      className="font-medium text-primary hover:underline break-words"
                                      target="_blank"
                                      rel="noopener noreferrer"
                                      title={articleLabel}
                                    >
                                      {articleLabel}
                                    </a>
                                  ) : (
                                    <span className="font-medium break-words" title={articleLabel}>
                                      {articleLabel}
                                    </span>
                                  )}
                                </div>
                              </div>
                            </TableCell>
                            <TableCell className="align-top py-3">
                              <Badge
                                variant="outline"
                                className={cn(
                                  "font-medium shadow-none",
                                  mentionNatureBadgeClass(m.mention_nature),
                                )}
                              >
                                {mentionNatureDisplayLabel(m.mention_nature)}
                              </Badge>
                            </TableCell>
                            <TableCell className="text-muted-foreground text-sm align-top max-w-[10rem] break-words leading-snug">
                              {m.description ?? "—"}
                            </TableCell>
                            <TableCell className="min-w-0 text-sm align-top break-words leading-relaxed">
                              {m.original_text ?? "—"}
                            </TableCell>
                            <TableCell className="align-top" />
                          </TableRow>
                          )
                        })
                      )}
                    </Fragment>
                  )
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <LocationMetaTab
        locationId={canonical.id}
        projectSlug={projectSlug}
        onMetaUpdated={() => void loadCanonical(canonical.id, projectSlug, true)}
      />

      <ConnectionsSection
        entityType="location"
        entityId={canonical.id}
        projectSlug={projectSlug}
        entityDisplayName={canonical.label}
      />

      <Dialog open={substrateGeometryOpen} onOpenChange={setSubstrateGeometryOpen}>
        <DialogContent className="max-w-3xl max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Substrate geometry</DialogTitle>
            <DialogDescription>
              {substrateGeometrySubstrate ? substrateGeometrySubstrate.name : "—"}
            </DialogDescription>
          </DialogHeader>

          {substrateGeometryLoading ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground py-4">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading geometry…
            </div>
          ) : !substrateGeometryJson ? (
            <p className="text-sm text-muted-foreground">No geometry found on this substrate.</p>
          ) : (
            <div className="space-y-3">
              <div className="h-[18rem] rounded-md border overflow-hidden">
                <LeafletMap
                  points={
                    geometryToFeatureCollections(substrateGeometryJson, {
                      featureId: "substrate",
                      label: "Substrate",
                      group: "substrate",
                    }).points as any
                  }
                  polygons={
                    geometryToFeatureCollections(substrateGeometryJson, {
                      featureId: "substrate",
                      label: "Substrate",
                      group: "substrate",
                    }).polygons as any
                  }
                  showPopups={false}
                  fitToData
                  initialCenter={ADD_GEOMETRY_MAP_CENTER}
                  initialZoom={ADD_GEOMETRY_MAP_ZOOM}
                />
              </div>
              <div className="rounded-md border bg-muted/30 p-3">
                <pre className="text-xs whitespace-pre-wrap break-words">
                  {JSON.stringify(substrateGeometryJson, null, 2)}
                </pre>
              </div>
            </div>
          )}

          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setSubstrateGeometryOpen(false)}>
              Close
            </Button>
            <Button
              variant="secondary"
              disabled={
                substrateGeometryLoading ||
                adoptingSubstrateGeometry ||
                !substrateGeometryJson ||
                !canonical
              }
              onClick={() => void handleAdoptSubstrateGeometry()}
            >
              {adoptingSubstrateGeometry ? "Adopting…" : "Adopt for canonical"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete canonical location</DialogTitle>
            <DialogDescription>
              Delete &quot;{canonical.label}&quot;? Linked places return to the candidate queue. This
              cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteOpen(false)} disabled={deleting}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={() => void onDelete()} disabled={deleting}>
              {deleting ? "Deleting…" : "Delete"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <CanonicalLinkModal
        open={moveSubstrateId !== null}
        onOpenChange={(o) => {
          if (!o) setMoveSubstrateId(null)
        }}
        projectSlug={projectSlug}
        substrateLocationId={moveSubstrateId}
        title="Move substrate to another canonical"
        onDone={() => void refreshCanonicalPage(true)}
      />
    </div>
  )
}
