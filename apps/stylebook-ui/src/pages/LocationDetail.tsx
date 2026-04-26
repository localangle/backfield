import { Fragment, useCallback, useEffect, useMemo, useState } from "react"
import { useNavigate, useParams, useSearchParams } from "react-router-dom"
import {
  deleteCanonicalLocation,
  getCanonicalLocation,
  getCanonicalLocationMentions,
  listCanonicalLinkedSubstrates,
  patchCanonicalLocation,
  unlinkSubstrateFromCanonical,
  type CanonicalLocation,
  type LinkedMention,
  type LinkedSubstrateItem,
} from "@/lib/api"
import { placeExtractTypeLabel } from "@/lib/place-extract-type-label"
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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Loader2, Trash2 } from "lucide-react"

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

export default function LocationDetail() {
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
  const [saving, setSaving] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [substrates, setSubstrates] = useState<LinkedSubstrateItem[]>([])
  const [substratesLoading, setSubstratesLoading] = useState(false)
  const [mentionsLoading, setMentionsLoading] = useState(false)
  const [moveSubstrateId, setMoveSubstrateId] = useState<number | null>(null)
  const [unlinkingId, setUnlinkingId] = useState<number | null>(null)
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
    [id, projectSlug, loadMentions, loadSubstrates],
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
      alert(e instanceof Error ? e.message : "Unlink failed")
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
      if (geometry) {
        await updateCanonicalLocationGeometry(canonicalId, projectSlug, geometry)
      }
      setCanonical(updated)
      setEditing(false)
      await loadCanonical(canonicalId, projectSlug)
      await loadSubstrates(canonicalId, projectSlug)
      await loadMentions(canonicalId, projectSlug)
    } catch (e) {
      console.error(e)
      alert(e instanceof Error ? e.message : "Save failed")
    } finally {
      setSaving(false)
    }
  }

  const onDelete = async () => {
    if (!canonical || !id || !projectSlug) return
    setDeleting(true)
    try {
      await deleteCanonicalLocation(id, projectSlug)
      navigate(`/locations/canonical?project=${projectSlug}`)
    } catch (e) {
      alert(e instanceof Error ? e.message : "Delete failed")
    } finally {
      setDeleting(false)
      setDeleteOpen(false)
    }
  }

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
        <div>
          <h1 className="text-3xl font-bold">{canonical.label}</h1>
          {canonical.slug ? (
            <p className="text-sm text-muted-foreground mt-1 font-mono">{canonical.slug}</p>
          ) : null}
        </div>
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
                    setGeometry((canonical.geometry_json as Record<string, unknown> | undefined) ?? null)
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
                    setGeometry((canonical.geometry_json as Record<string, unknown> | undefined) ?? null)
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

      {editing && (
        <Card>
          <CardHeader>
            <CardTitle>Geometry (GeoJSON)</CardTitle>
            <CardDescription>Updates canonical geometry when you save</CardDescription>
          </CardHeader>
          <CardContent>
            <SimpleGeoJsonGeometry value={geometry} onChange={setGeometry} />
          </CardContent>
        </Card>
      )}

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
                          <div className="font-medium">{s.name}</div>
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
