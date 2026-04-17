import { useEffect, useState } from "react"
import { useNavigate, useParams, useSearchParams } from "react-router-dom"
import {
  deleteLocation,
  getLocation,
  getLocationMentions,
  updateLocation,
  updateLocationGeometry,
  type Location,
  type LinkedMention,
} from "@/lib/api"
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
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Loader2, Trash2 } from "lucide-react"

export default function LocationDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [location, setLocation] = useState<Location | null>(null)
  const [mentions, setMentions] = useState<LinkedMention[]>([])
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState(false)
  const [projectSlug, setProjectSlug] = useState("")
  const [name, setName] = useState("")
  const [locationType, setLocationType] = useState("")
  const [formattedAddress, setFormattedAddress] = useState("")
  const [geometry, setGeometry] = useState<Record<string, unknown> | null>(null)
  const [saving, setSaving] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [deleting, setDeleting] = useState(false)

  useEffect(() => {
    const slug = searchParams.get("project") || ""
    setProjectSlug(slug)
  }, [searchParams])

  const loadLocation = async (locId: number, slug: string) => {
    try {
      setLoading(true)
      const loc = await getLocation(locId, slug)
      setLocation(loc)
      setName(loc.name)
      setLocationType(loc.location_type)
      setFormattedAddress(loc.formatted_address ?? "")
      setGeometry((loc.geometry_json as Record<string, unknown> | undefined) ?? null)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!id || !projectSlug) return
    void loadLocation(parseInt(id, 10), projectSlug)
  }, [id, projectSlug])

  useEffect(() => {
    if (!id || !projectSlug) return
    void (async () => {
      try {
        const m = await getLocationMentions(parseInt(id, 10), projectSlug)
        setMentions(m.mentions)
      } catch {
        setMentions([])
      }
    })()
  }, [id, projectSlug])

  const saveEdits = async () => {
    if (!location || !id || !projectSlug) return
    setSaving(true)
    try {
      const locId = parseInt(id, 10)
      const updated = await updateLocation(locId, projectSlug, {
        name,
        location_type: locationType,
        formatted_address: formattedAddress || undefined,
      })
      if (geometry) {
        await updateLocationGeometry(locId, projectSlug, geometry)
      }
      setLocation(updated)
      setEditing(false)
      await loadLocation(locId, projectSlug)
    } catch (e) {
      console.error(e)
      alert(e instanceof Error ? e.message : "Save failed")
    } finally {
      setSaving(false)
    }
  }

  const onDelete = async () => {
    if (!location || !id || !projectSlug) return
    setDeleting(true)
    try {
      await deleteLocation(parseInt(id, 10), projectSlug)
      navigate(`/locations/canonical?project=${projectSlug}`)
    } catch (e) {
      alert(e instanceof Error ? e.message : "Delete failed")
    } finally {
      setDeleting(false)
      setDeleteOpen(false)
    }
  }

  if (loading || !location) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <div className="container mx-auto p-6 space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-3xl font-bold">{location.name}</h1>
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
            {location.location_type} • {location.status}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4 max-w-xl">
          <div>
            <Label>Name</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} disabled={!editing} />
          </div>
          <div>
            <Label>Location type</Label>
            <Input
              value={locationType}
              onChange={(e) => setLocationType(e.target.value)}
              disabled={!editing}
            />
          </div>
          <div>
            <Label>Formatted address</Label>
            <Input
              value={formattedAddress}
              onChange={(e) => setFormattedAddress(e.target.value)}
              disabled={!editing}
            />
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
          <CardDescription>Linked articles for this canonical location</CardDescription>
        </CardHeader>
        <CardContent>
          {mentions.length === 0 ? (
            <p className="text-sm text-muted-foreground">No mentions returned for this project yet.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Article</TableHead>
                  <TableHead>Text</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {mentions.map((m) => (
                  <TableRow key={m.mention_id}>
                    <TableCell>{m.article_id}</TableCell>
                    <TableCell>{m.original_text ?? "—"}</TableCell>
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
            <DialogTitle>Delete location</DialogTitle>
            <DialogDescription>
              Delete &quot;{location.name}&quot;? This cannot be undone if the server allows deletion.
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
