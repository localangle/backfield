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
import { CanonicalLinkModal } from "@/components/CanonicalLinkModal"
import { updateCanonicalLocationGeometry } from "@/lib/stylebook-api/locations"
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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Loader2, Trash2 } from "lucide-react"

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

  const loadCanonical = async (canonicalId: number, slug: string, quiet = false) => {
    try {
      if (!quiet) setLoading(true)
      const row = await getCanonicalLocation(canonicalId, slug)
      setCanonical(row)
      setLabel(row.label)
      setGeometry((row.geometry_json as Record<string, unknown> | undefined) ?? null)
    } catch (e) {
      console.error(e)
    } finally {
      if (!quiet) setLoading(false)
    }
  }

  useEffect(() => {
    if (!id || !projectSlug) return
    void loadCanonical(parseInt(id, 10), projectSlug)
  }, [id, projectSlug])

  const loadMentions = useCallback(async (canonicalId: number, slug: string) => {
    setMentionsLoading(true)
    try {
      const m = await getCanonicalLocationMentions(canonicalId, slug, 500, 0)
      setMentions(m.mentions)
    } catch {
      setMentions([])
    } finally {
      setMentionsLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!id || !projectSlug) return
    void loadMentions(parseInt(id, 10), projectSlug)
  }, [id, projectSlug, loadMentions])

  const loadSubstrates = useCallback(async (canonicalId: number, slug: string) => {
    try {
      setSubstratesLoading(true)
      const r = await listCanonicalLinkedSubstrates(canonicalId, slug)
      setSubstrates(r.substrates)
    } catch {
      setSubstrates([])
    } finally {
      setSubstratesLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!id || !projectSlug) return
    void loadSubstrates(parseInt(id, 10), projectSlug)
  }, [id, projectSlug, loadSubstrates])

  const refreshCanonicalPage = useCallback(async () => {
    if (!id || !projectSlug) return
    const cid = parseInt(id, 10)
    await loadCanonical(cid, projectSlug, true)
    await loadSubstrates(cid, projectSlug)
    await loadMentions(cid, projectSlug)
  }, [id, projectSlug, loadMentions, loadSubstrates])

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
      await refreshCanonicalPage()
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
      const canonicalId = parseInt(id, 10)
      const updated = await patchCanonicalLocation(canonicalId, projectSlug, { label })
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
      await deleteCanonicalLocation(parseInt(id, 10), projectSlug)
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
        <h1 className="text-3xl font-bold">{canonical.label}</h1>
        <div className="flex gap-2">
          {editing ? (
            <>
              <Button variant="outline" onClick={() => setEditing(false)} disabled={saving}>
                Cancel
              </Button>
              <Button onClick={() => void saveEdits()} disabled={saving}>
                {saving ? "Saving…" : "Save"}
              </Button>
            </>
          ) : (
            <>
              <Button variant="outline" onClick={() => setEditing(true)}>
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
          <CardDescription>
            Stylebook canonical #{canonical.id} • {canonical.status} •{" "}
            {canonical.linked_substrate_count} linked substrate place
            {canonical.linked_substrate_count !== 1 ? "s" : ""} • {canonical.mention_count} mention
            {canonical.mention_count !== 1 ? "s" : ""}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4 max-w-xl">
          <div>
            <Label>Label</Label>
            <Input value={label} onChange={(e) => setLabel(e.target.value)} disabled={!editing} />
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
          <CardTitle>Places and article mentions</CardTitle>
          <CardDescription>
            Each row is a project substrate place linked to this canonical. Article mentions for
            that place appear indented underneath. Unlink returns only that substrate row to the open
            candidate queue (mentions unchanged). Move relinks it to another canonical in one step.
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
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[32%] min-w-[140px]">Place / article</TableHead>
                  <TableHead className="w-[14%]">Type / role</TableHead>
                  <TableHead>Quoted text</TableHead>
                  <TableHead className="text-right w-[150px]">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {substrates.map((s) => {
                  const group = mentionsBySubstrateId.get(s.id) ?? []
                  return (
                    <Fragment key={`group-${s.id}`}>
                      <TableRow className="bg-muted/50 border-t">
                        <TableCell colSpan={3} className="align-top py-3">
                          <div className="font-medium">{s.name}</div>
                          <div className="text-xs text-muted-foreground mt-0.5">
                            {s.location_type || "—"} · {s.normalized_name || "—"} ·{" "}
                            <span className="capitalize">{s.canonical_link_status}</span>
                          </div>
                        </TableCell>
                        <TableCell className="text-right align-top py-3 space-x-2 whitespace-nowrap">
                          <Button
                            size="sm"
                            variant="outline"
                            disabled={unlinkingId === s.id}
                            onClick={() => setMoveSubstrateId(s.id)}
                          >
                            Move…
                          </Button>
                          <Button
                            size="sm"
                            variant="secondary"
                            disabled={unlinkingId === s.id}
                            onClick={() => void handleUnlinkSubstrate(s)}
                          >
                            {unlinkingId === s.id ? "Unlinking…" : "Unlink"}
                          </Button>
                        </TableCell>
                      </TableRow>
                      {group.length === 0 ? (
                        <TableRow>
                          <TableCell colSpan={4} className="pl-8 text-sm text-muted-foreground py-2">
                            No article mentions for this place.
                          </TableCell>
                        </TableRow>
                      ) : (
                        group.map((m) => (
                          <TableRow key={m.mention_id} className="hover:bg-muted/30">
                            <TableCell className="pl-8 align-top">
                              <span className="text-muted-foreground mr-1 select-none" aria-hidden>
                                ↳
                              </span>
                              {m.article_url ? (
                                <a
                                  href={m.article_url}
                                  className="font-medium text-primary hover:underline"
                                  target="_blank"
                                  rel="noreferrer"
                                >
                                  {m.article_headline ?? `Article ${m.article_id}`}
                                </a>
                              ) : (
                                <span className="font-medium">
                                  {m.article_headline ?? `Article ${m.article_id}`}
                                </span>
                              )}
                            </TableCell>
                            <TableCell className="text-muted-foreground text-sm align-top whitespace-nowrap">
                              {m.description ?? "—"}
                            </TableCell>
                            <TableCell className="max-w-md text-sm align-top">
                              {m.original_text ?? "—"}
                            </TableCell>
                            <TableCell className="align-top" />
                          </TableRow>
                        ))
                      )}
                    </Fragment>
                  )
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete canonical location</DialogTitle>
            <DialogDescription>
              Delete &quot;{canonical.label}&quot;? Linked substrate places return to the candidate
              queue.
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
        onDone={() => void refreshCanonicalPage()}
      />
    </div>
  )
}
