import { useCallback, useEffect, useMemo, useState } from "react"
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
import { useProjectCatalogScope } from "@/lib/catalogNavigation"
import { usePromptDeleteEmptyCanonical } from "@/lib/usePromptDeleteEmptyCanonical"
import { useScopeBreadcrumbRoot } from "@/lib/breadcrumbs"
import { useCanEditStylebook } from "@/lib/stylebookEditContext"
import { useAppMessage } from "@/components/AppMessageProvider"
import { CanonicalLinkModal } from "@/components/CanonicalLinkModal"
import CanonicalDetailLayout from "@/components/CanonicalDetailLayout"
import LocationGeographySection, {
  geometryToFeatureCollections,
} from "@/components/LocationGeographySection"
import LocationMetaTab from "@/components/LocationMetaTab"
import { locationCanonicalDetailConfig } from "@/lib/entityConfigs/location/canonicalDetail"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { LeafletMap } from "@backfield/ui/LeafletMap"
import { updateCanonicalLocationGeometry } from "@/lib/stylebook-api/locations"
import { Loader2 } from "lucide-react"

/** Continental US when adding the first geometry from an empty draft (matches LeafletMap defaults). */
const ADD_GEOMETRY_MAP_CENTER: [number, number] = [39.8283, -98.5795]
/** Match @backfield/ui LeafletMap continental US default framing. */
const ADD_GEOMETRY_MAP_ZOOM = 3

export default function LocationDetail() {
  const { showError, showConfirm } = useAppMessage()
  const {
    projectFilterSlug,
    filterScopeSuffix,
    stylebookSlug,
    catalogBasePath,
  } = useProjectCatalogScope()
  const [searchParams] = useSearchParams()
  const crumbRoot = useScopeBreadcrumbRoot()
  const canEdit = useCanEditStylebook()
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [canonical, setCanonical] = useState<CanonicalLocation | null>(null)
  const [mentions, setMentions] = useState<LinkedMention[]>([])
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState(false)
  const evidenceProjectSlug = projectFilterSlug || ""
  const [label, setLabel] = useState("")
  const [locationType, setLocationType] = useState("")
  const [formattedAddress, setFormattedAddress] = useState("")
  const [saving, setSaving] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [substrates, setSubstrates] = useState<LinkedSubstrateItem[]>([])
  const [substratesLoading, setSubstratesLoading] = useState(false)
  const [mentionsLoading, setMentionsLoading] = useState(false)
  const [moveSubstrate, setMoveSubstrate] = useState<LinkedSubstrateItem | null>(null)
  const [unlinkingId, setUnlinkingId] = useState<number | null>(null)
  const [substrateGeometryOpen, setSubstrateGeometryOpen] = useState(false)
  const [substrateGeometryLoading, setSubstrateGeometryLoading] = useState(false)
  const [substrateGeometrySubstrate, setSubstrateGeometrySubstrate] =
    useState<LinkedSubstrateItem | null>(null)
  const [substrateGeometryJson, setSubstrateGeometryJson] = useState<Record<string, unknown> | null>(
    null,
  )
  const [adoptingSubstrateGeometry, setAdoptingSubstrateGeometry] = useState(false)

  const canonicalListHref = useMemo(() => {
    const base = `${catalogBasePath}/locations/canonical`
    const qs = searchParams.toString()
    if (qs) return `${base}?${qs}`
    return filterScopeSuffix ? `${base}${filterScopeSuffix}` : base
  }, [catalogBasePath, searchParams, filterScopeSuffix])

  const loadCanonical = useCallback(
    async (canonicalId: string, sbSlug: string, quiet = false) => {
      try {
        if (!quiet) setLoading(true)
        const row = await getCanonicalLocation(canonicalId, sbSlug, evidenceProjectSlug || undefined)
        setCanonical(row)
        setLabel(row.label)
        setLocationType(row.location_type ?? "")
        setFormattedAddress(row.formatted_address ?? "")
      } catch (e) {
        console.error(e)
      } finally {
        if (!quiet) setLoading(false)
      }
    },
    [evidenceProjectSlug],
  )

  useEffect(() => {
    if (!id || !stylebookSlug) return
    void loadCanonical(id, stylebookSlug)
  }, [id, stylebookSlug, evidenceProjectSlug, loadCanonical])

  const loadMentions = useCallback(
    async (canonicalId: string, sbSlug: string, quiet = false) => {
      if (!quiet) setMentionsLoading(true)
      try {
        const m = await getCanonicalLocationMentions(
          canonicalId,
          sbSlug,
          500,
          0,
          undefined,
          "desc",
          evidenceProjectSlug || undefined,
        )
        setMentions(m.mentions)
      } catch {
        setMentions([])
      } finally {
        if (!quiet) setMentionsLoading(false)
      }
    },
    [evidenceProjectSlug],
  )

  useEffect(() => {
    if (!id || !stylebookSlug) return
    void loadMentions(id, stylebookSlug)
  }, [id, stylebookSlug, loadMentions])

  const loadSubstrates = useCallback(
    async (canonicalId: string, sbSlug: string, quiet = false) => {
      if (!quiet) setSubstratesLoading(true)
      try {
        const r = await listCanonicalLinkedSubstrates(
          canonicalId,
          sbSlug,
          evidenceProjectSlug || undefined,
        )
        setSubstrates(r.substrates)
      } catch {
        setSubstrates([])
      } finally {
        if (!quiet) setSubstratesLoading(false)
      }
    },
    [evidenceProjectSlug],
  )

  useEffect(() => {
    if (!id || !stylebookSlug) return
    void loadSubstrates(id, stylebookSlug)
  }, [id, stylebookSlug, loadSubstrates])

  const refreshCanonicalPage = useCallback(
    async (quiet = false) => {
      if (!id || !stylebookSlug) return
      await loadCanonical(id, stylebookSlug, true)
      await loadSubstrates(id, stylebookSlug, quiet)
      await loadMentions(id, stylebookSlug, quiet)
    },
    [id, stylebookSlug, loadCanonical, loadMentions, loadSubstrates],
  )

  const tableLoading = substratesLoading || mentionsLoading

  const resetEditFieldsFromCanonical = useCallback((row: CanonicalLocation) => {
    setLabel(row.label)
    setLocationType(row.location_type ?? "")
    setFormattedAddress(row.formatted_address ?? "")
  }, [])

  async function handleUnlinkSubstrate(sub: LinkedSubstrateItem) {
    if (!sub.project_slug) {
      showError("Missing project for this linked place.")
      return
    }
    setUnlinkingId(sub.id)
    try {
      await unlinkSubstrateFromCanonical(sub.id, sub.project_slug)
      await refreshCanonicalPage(true)
    } catch (e) {
      showError(e instanceof Error ? e.message : "Unlink failed")
    } finally {
      setUnlinkingId(null)
    }
  }

  const saveEdits = async () => {
    if (!canonical || !id || !stylebookSlug) return
    setSaving(true)
    try {
      const canonicalId = id
      const updated = await patchCanonicalLocation(
        canonicalId,
        stylebookSlug,
        {
          label: label.trim(),
          location_type: locationType.trim() === "" ? null : locationType.trim().toLowerCase(),
          formatted_address: formattedAddress.trim() === "" ? null : formattedAddress.trim(),
        },
        evidenceProjectSlug || undefined,
      )
      setCanonical(updated)
      setEditing(false)
      await loadCanonical(canonicalId, stylebookSlug)
      await loadSubstrates(canonicalId, stylebookSlug)
      await loadMentions(canonicalId, stylebookSlug)
    } catch (e) {
      console.error(e)
      showError(e instanceof Error ? e.message : "Save failed")
    } finally {
      setSaving(false)
    }
  }

  const onDelete = useCallback(async () => {
    if (!canonical || !id || !stylebookSlug) return
    setDeleting(true)
    try {
      await deleteCanonicalLocation(id, stylebookSlug)
      navigate(canonicalListHref)
    } catch (e) {
      showError(e instanceof Error ? e.message : "Delete failed")
    } finally {
      setDeleting(false)
      setDeleteOpen(false)
    }
  }, [canonical, id, navigate, stylebookSlug, showError, canonicalListHref])

  usePromptDeleteEmptyCanonical({
    canonicalKey: `${stylebookSlug}:${evidenceProjectSlug}:${id ?? ""}`,
    enabled: Boolean(id),
    mentions,
    mentionsLoading,
    substrates,
    substratesLoading,
    showConfirm,
    onDelete,
  })

  const openSubstrateGeometry = useCallback(
    async (sub: LinkedSubstrateItem) => {
      if (!sub.project_slug) {
        showError("Missing project for this linked place.")
        return
      }
      setSubstrateGeometrySubstrate(sub)
      setSubstrateGeometryJson(null)
      setSubstrateGeometryOpen(true)
      setSubstrateGeometryLoading(true)
      try {
        const row = await getLocation(sub.id, sub.project_slug)
        const g = (row.geometry_json as Record<string, unknown> | undefined) ?? null
        setSubstrateGeometryJson(g)
      } catch (e) {
        showError(e instanceof Error ? e.message : "Could not load substrate geometry")
      } finally {
        setSubstrateGeometryLoading(false)
      }
    },
    [showError],
  )

  const handleAdoptSubstrateGeometry = useCallback(async () => {
    if (!canonical || !substrateGeometrySubstrate || !stylebookSlug) return
    if (!substrateGeometryJson || typeof substrateGeometryJson !== "object") return
    setAdoptingSubstrateGeometry(true)
    try {
      await updateCanonicalLocationGeometry(canonical.id, stylebookSlug, substrateGeometryJson)
      await loadCanonical(canonical.id, stylebookSlug, true)
      setSubstrateGeometryOpen(false)
    } catch (e) {
      showError(e instanceof Error ? e.message : "Could not adopt geometry")
    } finally {
      setAdoptingSubstrateGeometry(false)
    }
  }, [
    canonical,
    loadCanonical,
    stylebookSlug,
    showError,
    substrateGeometryJson,
    substrateGeometrySubstrate,
  ])

  const mentionsConfig = useMemo(
    () => ({
      ...locationCanonicalDetailConfig.mentions,
      renderSubstrateHeaderExtra: (s: LinkedSubstrateItem) => (
        <button
          type="button"
          className="relative z-10 text-xs text-primary hover:underline shrink-0"
          onClick={() => void openSubstrateGeometry(s)}
        >
          View geometry
        </button>
      ),
    }),
    [openSubstrateGeometry],
  )

  const geometry = (canonical?.geometry_json as Record<string, unknown> | undefined) ?? null

  return (
    <CanonicalDetailLayout
      config={locationCanonicalDetailConfig}
      loading={loading || !canonical}
      breadcrumbs={[
        { label: crumbRoot.label, to: crumbRoot.to },
        { label: locationCanonicalDetailConfig.listBreadcrumbLabel, to: canonicalListHref },
        { label: canonical?.label ?? "" },
      ]}
      title={canonical?.label ?? ""}
      editing={editing}
      saving={saving}
      canEdit={canEdit}
      onStartEdit={() => {
        if (canonical) resetEditFieldsFromCanonical(canonical)
        setEditing(true)
      }}
      onCancelEdit={() => {
        if (canonical) resetEditFieldsFromCanonical(canonical)
        setEditing(false)
      }}
      onSave={() => void saveEdits()}
      onDeleteClick={() => setDeleteOpen(true)}
      deleteOpen={deleteOpen}
      onDeleteOpenChange={setDeleteOpen}
      deleting={deleting}
      onDelete={onDelete}
      stylebookSlug={stylebookSlug}
      entityId={canonical?.id}
      entityDisplayName={canonical?.label}
      details={
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
                <p className="text-sm mt-1.5">{canonical?.label || "—"}</p>
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
                <p className="text-sm mt-1.5">
                  {canonical?.location_type ? placeExtractTypeLabel(canonical.location_type) : "—"}
                </p>
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
                <p className="text-sm mt-1.5">{canonical?.formatted_address || "—"}</p>
              )}
            </div>
          </CardContent>
        </Card>
      }
      geography={
        canonical && stylebookSlug ? (
          <LocationGeographySection
            canonicalId={canonical.id}
            stylebookSlug={stylebookSlug}
            geometry={geometry}
            canEdit={canEdit}
            onGeometrySaved={() => loadCanonical(canonical.id, stylebookSlug, true)}
          />
        ) : null
      }
      mentions={{
        config: mentionsConfig,
        substrates,
        mentions,
        loading: tableLoading,
        unlinkingId,
        onUnlink: (s) => void handleUnlinkSubstrate(s),
        onMove: setMoveSubstrate,
      }}
      meta={
        canonical && stylebookSlug ? (
          <LocationMetaTab
            locationId={canonical.id}
            stylebookSlug={stylebookSlug}
            onMetaUpdated={() => void loadCanonical(canonical.id, stylebookSlug, true)}
          />
        ) : null
      }
    >
      <Dialog open={substrateGeometryOpen} onOpenChange={setSubstrateGeometryOpen}>
        <DialogContent className="max-w-3xl max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Instance Geometry</DialogTitle>
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
                      label: "Instance",
                      group: "substrate",
                    }).points as Parameters<typeof LeafletMap>[0]["points"]
                  }
                  polygons={
                    geometryToFeatureCollections(substrateGeometryJson, {
                      featureId: "substrate",
                      label: "Instance",
                      group: "substrate",
                    }).polygons as Parameters<typeof LeafletMap>[0]["polygons"]
                  }
                  showPopups={false}
                  fitToData
                  initialCenter={ADD_GEOMETRY_MAP_CENTER}
                  initialZoom={ADD_GEOMETRY_MAP_ZOOM}
                />
              </div>
              <details className="rounded-md border bg-muted/30 group">
                <summary className="cursor-pointer select-none px-3 py-2 text-sm font-medium text-foreground list-none [&::-webkit-details-marker]:hidden flex items-center gap-2">
                  <span className="text-muted-foreground group-open:hidden">▸</span>
                  <span className="text-muted-foreground hidden group-open:inline">▾</span>
                  GeoJSON
                </summary>
                <div className="border-t px-3 pb-3 pt-1">
                  <pre className="text-xs whitespace-pre-wrap break-words max-h-[12rem] overflow-y-auto">
                    {JSON.stringify(substrateGeometryJson, null, 2)}
                  </pre>
                </div>
              </details>
            </div>
          )}

          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setSubstrateGeometryOpen(false)}>
              Close
            </Button>
            <Button
              className="bg-black text-white hover:bg-black/90 focus-visible:ring-black/40"
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

      {moveSubstrate ? (
        <CanonicalLinkModal
          open={moveSubstrate !== null}
          onOpenChange={(o) => {
            if (!o) setMoveSubstrate(null)
          }}
          projectSlug={moveSubstrate.project_slug}
          stylebookSlug={stylebookSlug}
          substrateLocationId={moveSubstrate.id}
          excludeCanonicalId={canonical?.id ?? ""}
          title="Move linked place to another canonical"
          onDone={() => void refreshCanonicalPage(true)}
        />
      ) : null}
    </CanonicalDetailLayout>
  )
}
