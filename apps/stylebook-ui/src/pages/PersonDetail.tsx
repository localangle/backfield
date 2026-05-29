import { useCallback, useEffect, useMemo, useState } from "react"
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom"
import {
  deleteCanonicalPerson,
  getCanonicalPerson,
  listCanonicalPersonTypes,
  patchCanonicalPerson,
  type CanonicalPerson,
} from "@/lib/api"
import { placeExtractTypeLabel, sortReviewQueueTypeFilterOptions } from "@/lib/place-extract-type-label"
import { useProjectCatalogScope } from "@/lib/catalogNavigation"
import { useScopeBreadcrumbRoot } from "@/lib/breadcrumbs"
import { useCanEditStylebook } from "@/lib/stylebookEditContext"
import { useAppMessage } from "@/components/AppMessageProvider"
import { Breadcrumbs } from "@/components/Breadcrumbs"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import ConnectionsSection from "@/components/ConnectionsSection"
import { Loader2, Trash2 } from "lucide-react"

export default function PersonDetail() {
  const { showError } = useAppMessage()
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
  const [person, setPerson] = useState<CanonicalPerson | null>(null)
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState(false)
  const [label, setLabel] = useState("")
  const [title, setTitle] = useState("")
  const [affiliation, setAffiliation] = useState("")
  const [personType, setPersonType] = useState("")
  const [publicFigure, setPublicFigure] = useState(false)
  const [types, setTypes] = useState<string[]>([])
  const [saving, setSaving] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [deleting, setDeleting] = useState(false)

  const canonicalListHref = useMemo(() => {
    const base = `${catalogBasePath}/people/canonical`
    const qs = searchParams.toString()
    if (qs) return `${base}?${qs}`
    return filterScopeSuffix ? `${base}${filterScopeSuffix}` : base
  }, [catalogBasePath, searchParams, filterScopeSuffix])

  const orderedTypeOptions = useMemo(
    () => sortReviewQueueTypeFilterOptions(types),
    [types],
  )

  const loadPerson = useCallback(
    async (canonicalId: string, sbSlug: string) => {
      try {
        setLoading(true)
        const row = await getCanonicalPerson(
          canonicalId,
          sbSlug,
          projectFilterSlug || undefined,
        )
        setPerson(row)
        setLabel(row.label)
        setTitle(row.title ?? "")
        setAffiliation(row.affiliation ?? "")
        setPersonType(row.person_type ?? "")
        setPublicFigure(row.public_figure)
      } catch (e) {
        console.error(e)
        setPerson(null)
      } finally {
        setLoading(false)
      }
    },
    [projectFilterSlug],
  )

  useEffect(() => {
    if (!id || !stylebookSlug) return
    void loadPerson(id, stylebookSlug)
  }, [id, stylebookSlug, loadPerson])

  useEffect(() => {
    if (!stylebookSlug) return
    void (async () => {
      try {
        const res = await listCanonicalPersonTypes(stylebookSlug)
        setTypes(res.types)
      } catch {
        setTypes([])
      }
    })()
  }, [stylebookSlug])

  async function handleSave() {
    if (!person || !stylebookSlug) return
    const trimmedLabel = label.trim()
    if (!trimmedLabel) {
      showError("Name is required")
      return
    }
    setSaving(true)
    try {
      await patchCanonicalPerson(
        person.id,
        stylebookSlug,
        {
          label: trimmedLabel,
          title: title.trim() || null,
          affiliation: affiliation.trim() || null,
          person_type: personType.trim() || null,
          public_figure: publicFigure,
        },
        projectFilterSlug || undefined,
      )
      setEditing(false)
      await loadPerson(person.id, stylebookSlug)
    } catch (e) {
      console.error(e)
      showError("Failed to save person")
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete() {
    if (!person || !stylebookSlug) return
    setDeleting(true)
    try {
      await deleteCanonicalPerson(person.id, stylebookSlug)
      setDeleteOpen(false)
      navigate(canonicalListHref)
    } catch (e) {
      console.error(e)
      showError("Failed to delete person")
    } finally {
      setDeleting(false)
    }
  }

  if (loading) {
    return (
      <div className="container mx-auto p-6 flex justify-center py-16">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (!person) {
    return (
      <div className="container mx-auto p-6">
        <p className="text-muted-foreground">Person not found.</p>
        <Button variant="outline" className="mt-4" asChild>
          <Link to={canonicalListHref}>Back to people</Link>
        </Button>
      </div>
    )
  }

  return (
    <div className="container mx-auto p-6 space-y-6">
      <div className="flex justify-between items-start gap-4">
        <div className="min-w-0">
          <Breadcrumbs
            className="mb-3"
            items={[
              { label: crumbRoot.label, to: crumbRoot.to },
              { label: "People", to: canonicalListHref },
              { label: person.label },
            ]}
          />
          <h1 className="text-3xl font-bold">{person.label}</h1>
        </div>
        <Button variant="outline" asChild>
          <Link to={canonicalListHref}>Back to people</Link>
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Details</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {editing ? (
            <>
              <div className="space-y-2">
                <Label htmlFor="person-label">Name</Label>
                <Input
                  id="person-label"
                  value={label}
                  onChange={(e) => setLabel(e.target.value)}
                  disabled={!canEdit || saving}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="person-title">Title</Label>
                <Input
                  id="person-title"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  disabled={!canEdit || saving}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="person-affiliation">Affiliation</Label>
                <Input
                  id="person-affiliation"
                  value={affiliation}
                  onChange={(e) => setAffiliation(e.target.value)}
                  disabled={!canEdit || saving}
                />
              </div>
              <div className="space-y-2">
                <Label>Type</Label>
                <Select
                  value={personType || "none"}
                  onValueChange={(v) => setPersonType(v === "none" ? "" : v)}
                  disabled={!canEdit || saving}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select type" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">None</SelectItem>
                    {orderedTypeOptions.map((t) => (
                      <SelectItem key={t} value={t}>
                        {placeExtractTypeLabel(t)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex items-center gap-2">
                <Checkbox
                  id="person-public-figure"
                  checked={publicFigure}
                  onCheckedChange={(v) => setPublicFigure(v === true)}
                  disabled={!canEdit || saving}
                />
                <Label htmlFor="person-public-figure">Public figure</Label>
              </div>
              <div className="flex gap-2">
                <Button onClick={() => void handleSave()} disabled={!canEdit || saving}>
                  {saving ? "Saving…" : "Save"}
                </Button>
                <Button variant="outline" onClick={() => setEditing(false)} disabled={saving}>
                  Cancel
                </Button>
              </div>
            </>
          ) : (
            <>
              <div>
                <span className="text-muted-foreground">Name:</span> {person.label}
              </div>
              {person.title ? (
                <div>
                  <span className="text-muted-foreground">Title:</span> {person.title}
                </div>
              ) : null}
              {person.affiliation ? (
                <div>
                  <span className="text-muted-foreground">Affiliation:</span> {person.affiliation}
                </div>
              ) : null}
              {person.person_type ? (
                <div>
                  <span className="text-muted-foreground">Type:</span>{" "}
                  {placeExtractTypeLabel(person.person_type)}
                </div>
              ) : null}
              <div>
                <span className="text-muted-foreground">Public figure:</span>{" "}
                {person.public_figure ? "Yes" : "No"}
              </div>
              <div>
                <span className="text-muted-foreground">Status:</span> {person.status}
              </div>
              <div className="flex gap-2">
                <Button onClick={() => setEditing(true)} disabled={!canEdit}>
                  Edit
                </Button>
                <Button
                  variant="destructive"
                  onClick={() => setDeleteOpen(true)}
                  disabled={!canEdit}
                >
                  <Trash2 className="h-4 w-4 mr-2" />
                  Delete
                </Button>
              </div>
            </>
          )}
        </CardContent>
      </Card>

      {stylebookSlug ? (
        <ConnectionsSection
          entityType="person"
          entityId={person.id}
          stylebookSlug={stylebookSlug}
          entityDisplayName={person.label}
        />
      ) : null}

      <Dialog open={deleteOpen} onOpenChange={(open) => !deleting && setDeleteOpen(open)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete person</DialogTitle>
            <DialogDescription>
              Delete &quot;{person.label}&quot;? Linked people return to the candidate queue. This
              cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteOpen(false)} disabled={deleting}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={() => void handleDelete()} disabled={deleting}>
              {deleting ? "Deleting…" : "Delete"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
