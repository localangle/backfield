import { Fragment, useCallback, useEffect, useMemo, useState } from "react"
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom"
import {
  deleteCanonicalPerson,
  getCanonicalPerson,
  getCanonicalPersonMentions,
  listCanonicalLinkedPersonSubstrates,
  patchCanonicalPerson,
  unlinkPersonSubstrateFromCanonical,
  type CanonicalPerson,
  type LinkedPersonMention,
  type LinkedPersonSubstrateItem,
} from "@/lib/api"
import {
  personTypeManualSelectOptions,
  placeExtractTypeLabel,
} from "@/lib/place-extract-type-label"
import { personNatureBadgeClass, personNatureDisplayLabel } from "@/lib/personMentionNature"
import { useProjectCatalogScope } from "@/lib/catalogNavigation"
import { usePromptDeleteEmptyCanonical } from "@/lib/usePromptDeleteEmptyCanonical"
import { useScopeBreadcrumbRoot } from "@/lib/breadcrumbs"
import { useCanEditStylebook } from "@/lib/stylebookEditContext"
import { useAppMessage } from "@/components/AppMessageProvider"
import { PersonCanonicalLinkModal } from "@/components/PersonCanonicalLinkModal"
import PersonMetaTab from "@/components/PersonMetaTab"
import { Breadcrumbs } from "@/components/Breadcrumbs"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import ConnectionsSection from "@/components/ConnectionsSection"
import { cn } from "@/lib/utils"
import { Loader2, Trash2 } from "lucide-react"

function derivePersonSortKey(label: string, explicit?: string | null): string {
  const normalize = (value: string) => value.trim().toLowerCase().replace(/\s+/g, " ")
  const fromExplicit = explicit != null ? normalize(explicit) : ""
  if (fromExplicit) return fromExplicit
  const parts = label.trim().split(/\s+/)
  if (parts.length >= 2) return normalize(parts[parts.length - 1]!)
  return normalize(parts[0] ?? "")
}

function mentionArticleDisplayTitle(m: LinkedPersonMention): string {
  const trimmed = (m.article_headline ?? "").trim()
  if (trimmed.length > 0) return trimmed
  return `Article ${m.article_id}`
}

function mentionArticleHref(m: LinkedPersonMention): string | null {
  const u = (m.article_url ?? "").trim()
  return u.length > 0 ? u : null
}

export default function PersonDetail() {
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
  const evidenceProjectSlug = projectFilterSlug || ""

  const [person, setPerson] = useState<CanonicalPerson | null>(null)
  const [substrates, setSubstrates] = useState<LinkedPersonSubstrateItem[]>([])
  const [mentions, setMentions] = useState<LinkedPersonMention[]>([])
  const [loading, setLoading] = useState(true)
  const [substratesLoading, setSubstratesLoading] = useState(false)
  const [mentionsLoading, setMentionsLoading] = useState(false)
  const [editing, setEditing] = useState(false)
  const [label, setLabel] = useState("")
  const [title, setTitle] = useState("")
  const [affiliation, setAffiliation] = useState("")
  const [personType, setPersonType] = useState("")
  const [publicFigure, setPublicFigure] = useState(false)
  const [sortKey, setSortKey] = useState("")
  const [saving, setSaving] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [unlinkingId, setUnlinkingId] = useState<number | null>(null)
  const [moveSubstrate, setMoveSubstrate] = useState<LinkedPersonSubstrateItem | null>(null)

  const canonicalListHref = useMemo(() => {
    const base = `${catalogBasePath}/people/canonical`
    const qs = searchParams.toString()
    if (qs) return `${base}?${qs}`
    return filterScopeSuffix ? `${base}${filterScopeSuffix}` : base
  }, [catalogBasePath, searchParams, filterScopeSuffix])

  const orderedTypeOptions = useMemo(
    () => personTypeManualSelectOptions(personType),
    [personType],
  )

  const loadPerson = useCallback(
    async (canonicalId: string, sbSlug: string, quiet = false) => {
      try {
        if (!quiet) setLoading(true)
        const row = await getCanonicalPerson(
          canonicalId,
          sbSlug,
          evidenceProjectSlug || undefined,
        )
        setPerson(row)
        setLabel(row.label)
        setTitle(row.title ?? "")
        setAffiliation(row.affiliation ?? "")
        setPersonType(row.person_type ?? "")
        setPublicFigure(row.public_figure)
        setSortKey(row.sort_key ?? derivePersonSortKey(row.label))
      } catch (e) {
        console.error(e)
        if (!quiet) setPerson(null)
      } finally {
        if (!quiet) setLoading(false)
      }
    },
    [evidenceProjectSlug],
  )

  const loadSubstrates = useCallback(
    async (canonicalId: string, sbSlug: string, quiet = false) => {
      if (!quiet) setSubstratesLoading(true)
      try {
        const r = await listCanonicalLinkedPersonSubstrates(
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

  const loadMentions = useCallback(
    async (canonicalId: string, sbSlug: string, quiet = false) => {
      if (!quiet) setMentionsLoading(true)
      try {
        const m = await getCanonicalPersonMentions(
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

  const refreshCanonicalPage = useCallback(
    async (quiet = false) => {
      if (!id || !stylebookSlug) return
      await loadPerson(id, stylebookSlug, true)
      await loadSubstrates(id, stylebookSlug, quiet)
      await loadMentions(id, stylebookSlug, quiet)
    },
    [id, stylebookSlug, loadPerson, loadSubstrates, loadMentions],
  )

  useEffect(() => {
    if (!id || !stylebookSlug) return
    void loadPerson(id, stylebookSlug)
  }, [id, stylebookSlug, loadPerson])

  useEffect(() => {
    if (!id || !stylebookSlug) return
    void loadSubstrates(id, stylebookSlug)
  }, [id, stylebookSlug, loadSubstrates])

  useEffect(() => {
    if (!id || !stylebookSlug) return
    void loadMentions(id, stylebookSlug)
  }, [id, stylebookSlug, loadMentions])

  const mentionsBySubstrateId = useMemo(() => {
    const map = new Map<number, LinkedPersonMention[]>()
    for (const row of mentions) {
      const sid = row.substrate_person_id
      if (!map.has(sid)) map.set(sid, [])
      map.get(sid)!.push(row)
    }
    return map
  }, [mentions])

  const tableLoading = substratesLoading || mentionsLoading

  async function handleUnlinkSubstrate(sub: LinkedPersonSubstrateItem) {
    if (!sub.project_slug) {
      showError("Missing project for this linked person.")
      return
    }
    setUnlinkingId(sub.id)
    try {
      await unlinkPersonSubstrateFromCanonical(sub.id, sub.project_slug)
      await refreshCanonicalPage(true)
    } catch (e) {
      showError(e instanceof Error ? e.message : "Unlink failed")
    } finally {
      setUnlinkingId(null)
    }
  }

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
          sort_key: sortKey.trim() || null,
        },
        evidenceProjectSlug || undefined,
      )
      setEditing(false)
      await refreshCanonicalPage(true)
    } catch (e) {
      console.error(e)
      showError("Failed to save person")
    } finally {
      setSaving(false)
    }
  }

  function resetEditFieldsFromPerson(row: CanonicalPerson) {
    setLabel(row.label)
    setTitle(row.title ?? "")
    setAffiliation(row.affiliation ?? "")
    setPersonType(row.person_type ?? "")
    setPublicFigure(row.public_figure)
    setSortKey(row.sort_key ?? derivePersonSortKey(row.label))
  }

  const onDelete = useCallback(async () => {
    if (!person || !id || !stylebookSlug) return
    setDeleting(true)
    try {
      await deleteCanonicalPerson(id, stylebookSlug)
      navigate(canonicalListHref)
    } catch (e) {
      console.error(e)
      showError(e instanceof Error ? e.message : "Delete failed")
    } finally {
      setDeleting(false)
      setDeleteOpen(false)
    }
  }, [person, id, stylebookSlug, navigate, canonicalListHref, showError])

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
      <div className="flex justify-between items-center">
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
        <div className="flex gap-2">
          {editing ? (
            <>
              <Button
                variant="outline"
                onClick={() => {
                  resetEditFieldsFromPerson(person)
                  setEditing(false)
                }}
                disabled={saving}
              >
                Cancel
              </Button>
              <Button onClick={() => void handleSave()} disabled={!canEdit || saving}>
                {saving ? "Saving…" : "Save"}
              </Button>
            </>
          ) : (
            <>
              <Button
                variant="outline"
                onClick={() => {
                  resetEditFieldsFromPerson(person)
                  setEditing(true)
                }}
                disabled={!canEdit}
              >
                Edit
              </Button>
              <Button
                variant="destructive"
                size="icon"
                onClick={() => setDeleteOpen(true)}
                disabled={!canEdit}
              >
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
        <CardContent className="space-y-3">
          {editing ? (
            <>
              <div className="space-y-1">
                <Label htmlFor="person-label" className="text-xs font-medium">
                  Name
                </Label>
                <Input
                  id="person-label"
                  className="h-8 text-xs"
                  value={label}
                  onChange={(e) => setLabel(e.target.value)}
                  disabled={!canEdit || saving}
                />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div className="min-w-0 space-y-1">
                  <Label htmlFor="person-title" className="text-xs font-medium">
                    Title
                  </Label>
                  <Input
                    id="person-title"
                    className="h-8 text-xs"
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    disabled={!canEdit || saving}
                  />
                </div>
                <div className="min-w-0 space-y-1">
                  <Label htmlFor="person-affiliation" className="text-xs font-medium">
                    Affiliation
                  </Label>
                  <Input
                    id="person-affiliation"
                    className="h-8 text-xs"
                    value={affiliation}
                    onChange={(e) => setAffiliation(e.target.value)}
                    disabled={!canEdit || saving}
                  />
                </div>
              </div>
              <div className="space-y-1">
                <Label htmlFor="person-type" className="text-xs font-medium">
                  Type
                </Label>
                <Select
                  value={personType || "none"}
                  onValueChange={(v) => setPersonType(v === "none" ? "" : v)}
                  disabled={!canEdit || saving}
                >
                  <SelectTrigger id="person-type" className="h-8 text-xs">
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
              <div className="grid grid-cols-2 items-end gap-2">
                <div className="flex items-center gap-2 pb-1">
                  <Label htmlFor="person-public-figure" className="shrink-0 text-xs font-medium">
                    Public figure
                  </Label>
                  <Switch
                    id="person-public-figure"
                    checked={publicFigure}
                    onCheckedChange={setPublicFigure}
                    disabled={!canEdit || saving}
                  />
                </div>
                <div className="min-w-0 space-y-1">
                  <Label htmlFor="person-sort-key" className="text-xs font-medium">
                    Sort key
                  </Label>
                  <Input
                    id="person-sort-key"
                    className="h-8 text-xs"
                    value={sortKey}
                    onChange={(e) => setSortKey(e.target.value)}
                    disabled={!canEdit || saving}
                    placeholder="Last name"
                  />
                </div>
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
              {person.sort_key ? (
                <div>
                  <span className="text-muted-foreground">Sort key:</span> {person.sort_key}
                </div>
              ) : null}
            </>
          )}
        </CardContent>
      </Card>

      <Card className="relative z-10">
        <CardHeader>
          <CardTitle>Mentions</CardTitle>
          <CardDescription>
            Article mentions are grouped by linked person. Unlink or reassign people below.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {tableLoading ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground py-4">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading…
            </div>
          ) : substrates.length === 0 ? (
            <p className="text-sm text-muted-foreground">No linked mentions.</p>
          ) : (
            <div className="w-full overflow-x-auto">
              <Table className="w-full min-w-[56rem]">
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-[26%] min-w-[9rem]">Person / article</TableHead>
                    <TableHead className="w-[6.5rem] min-w-[5.5rem]">Nature</TableHead>
                    <TableHead className="w-[10rem] min-w-[10rem]">Role in story</TableHead>
                    <TableHead className="min-w-[18rem]">Quoted text</TableHead>
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
                            <div className="font-medium min-w-0 break-words">{s.name}</div>
                            <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground break-words">
                              <Badge variant="outline" className="font-normal">
                                Project: {s.project_name}
                              </Badge>
                              {(s.person_type || "").trim()
                                ? placeExtractTypeLabel(s.person_type!)
                                : "—"}
                              {s.title ? (
                                <>
                                  <span className="text-muted-foreground/70">·</span>
                                  {s.title}
                                </>
                              ) : null}
                              {s.affiliation ? (
                                <>
                                  <span className="text-muted-foreground/70">·</span>
                                  {s.affiliation}
                                </>
                              ) : null}
                            </div>
                          </TableCell>
                          <TableCell className="text-right align-top py-3 w-[12rem] min-w-[12rem]">
                            <div className="flex flex-wrap justify-end gap-2">
                              <Button
                                type="button"
                                size="sm"
                                variant="outline"
                                className="relative z-10 shrink-0"
                                disabled={unlinkingId === s.id}
                                onClick={() => setMoveSubstrate(s)}
                              >
                                Move…
                              </Button>
                              <Button
                                type="button"
                                size="sm"
                                variant="secondary"
                                className="relative z-10 shrink-0"
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
                              No article mentions for this person.
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
                                      personNatureBadgeClass(m.mention_nature ?? ""),
                                    )}
                                  >
                                    {personNatureDisplayLabel(m.mention_nature ?? "")}
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
            </div>
          )}
        </CardContent>
      </Card>

      {stylebookSlug ? (
        <>
          <PersonMetaTab
            personId={person.id}
            stylebookSlug={stylebookSlug}
            onMetaUpdated={() => void loadPerson(person.id, stylebookSlug, true)}
          />

          <ConnectionsSection
            entityType="person"
            entityId={person.id}
            stylebookSlug={stylebookSlug}
            entityDisplayName={person.label}
          />
        </>
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
            <Button variant="destructive" onClick={() => void onDelete()} disabled={deleting}>
              {deleting ? "Deleting…" : "Delete"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {moveSubstrate ? (
        <PersonCanonicalLinkModal
          open={moveSubstrate !== null}
          onOpenChange={(o) => {
            if (!o) setMoveSubstrate(null)
          }}
          projectSlug={moveSubstrate.project_slug}
          substratePersonId={moveSubstrate.id}
          excludeCanonicalId={person.id}
          title="Move linked person to another canonical"
          onDone={() => void refreshCanonicalPage(true)}
        />
      ) : null}
    </div>
  )
}
