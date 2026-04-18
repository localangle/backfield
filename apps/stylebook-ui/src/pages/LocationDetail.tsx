import { useCallback, useEffect, useState } from "react"
import { useNavigate, useParams, useSearchParams } from "react-router-dom"
import {
  deleteCanonicalLocation,
  getCanonicalLocation,
  getCanonicalLocationMentions,
  patchCanonicalLocation,
  type CanonicalLocation,
  type LinkedMention,
} from "@/lib/api"
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

  useEffect(() => {
    const slug = searchParams.get("project") || ""
    setProjectSlug(slug)
  }, [searchParams])

  const loadCanonical = async (canonicalId: number, slug: string) => {
    try {
      setLoading(true)
      const row = await getCanonicalLocation(canonicalId, slug)
      setCanonical(row)
      setLabel(row.label)
      setGeometry((row.geometry_json as Record<string, unknown> | undefined) ?? null)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!id || !projectSlug) return
    void loadCanonical(parseInt(id, 10), projectSlug)
  }, [id, projectSlug])

  const loadMentions = useCallback(async (canonicalId: number, slug: string) => {
    try {
      const m = await getCanonicalLocationMentions(canonicalId, slug)
      setMentions(m.mentions)
    } catch {
      setMentions([])
    }
  }, [])

  useEffect(() => {
    if (!id || !projectSlug) return
    void loadMentions(parseInt(id, 10), projectSlug)
  }, [id, projectSlug, loadMentions])

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
          <CardTitle>Article mentions</CardTitle>
          <CardDescription>
            Mentions on any substrate location in this project linked to this canonical.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {mentions.length === 0 ? (
            <p className="text-sm text-muted-foreground">No article mentions yet.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Article</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead>Quoted text</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {mentions.map((m) => (
                  <TableRow key={m.mention_id}>
                    <TableCell className="max-w-xs">
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
                        <span className="font-medium">{m.article_headline ?? `Article ${m.article_id}`}</span>
                      )}
                    </TableCell>
                    <TableCell className="text-muted-foreground whitespace-nowrap">
                      {m.description ?? "—"}
                    </TableCell>
                    <TableCell className="max-w-md">{m.original_text ?? "—"}</TableCell>
                  </TableRow>
                ))}
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
    </div>
  )
}
