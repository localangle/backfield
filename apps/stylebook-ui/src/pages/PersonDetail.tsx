import { useCallback, useEffect, useMemo, useState } from "react"
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
import { isStylebookApiNotFoundError } from "@/lib/stylebook-api/client"
import { useProjectCatalogScope } from "@/lib/catalogNavigation"
import { usePromptDeleteEmptyCanonical } from "@/lib/usePromptDeleteEmptyCanonical"
import { useScopeBreadcrumbRoot } from "@/lib/breadcrumbs"
import { useCanEditStylebook } from "@/lib/stylebookEditContext"
import { useAppMessage } from "@/components/AppMessageProvider"
import { PersonCanonicalLinkModal } from "@/components/PersonCanonicalLinkModal"
import CanonicalDetailLayout from "@/components/CanonicalDetailLayout"
import PersonMetaTab from "@/components/PersonMetaTab"
import { personCanonicalDetailConfig } from "@/lib/entityConfigs/person/canonicalDetail"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"

function derivePersonSortKey(label: string, explicit?: string | null): string {
  const normalize = (value: string) => value.trim().toLowerCase().replace(/\s+/g, " ")
  const fromExplicit = explicit != null ? normalize(explicit) : ""
  if (fromExplicit) return fromExplicit
  const parts = label.trim().split(/\s+/)
  if (parts.length >= 2) return normalize(parts[parts.length - 1]!)
  return normalize(parts[0] ?? "")
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
    async (canonicalId: string, sbSlug: string, quiet = false): Promise<boolean> => {
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
        return true
      } catch (e) {
        if (isStylebookApiNotFoundError(e)) {
          setPerson(null)
          return false
        }
        console.error(e)
        if (!quiet) setPerson(null)
        return false
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
      if (!id || !stylebookSlug || deleting) return
      const found = await loadPerson(id, stylebookSlug, true)
      if (!found) {
        setSubstrates([])
        setMentions([])
        return
      }
      await loadSubstrates(id, stylebookSlug, quiet)
      await loadMentions(id, stylebookSlug, quiet)
    },
    [id, stylebookSlug, deleting, loadPerson, loadSubstrates, loadMentions],
  )

  useEffect(() => {
    if (!id || !stylebookSlug || deleting) return
    void loadPerson(id, stylebookSlug)
  }, [id, stylebookSlug, deleting, loadPerson])

  useEffect(() => {
    if (!id || !stylebookSlug || deleting || person?.id !== id) return
    void loadSubstrates(id, stylebookSlug)
  }, [id, stylebookSlug, deleting, person, loadSubstrates])

  useEffect(() => {
    if (!id || !stylebookSlug || deleting || person?.id !== id) return
    void loadMentions(id, stylebookSlug)
  }, [id, stylebookSlug, deleting, person, loadMentions])

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
    if (!id || !stylebookSlug) return
    setDeleting(true)
    try {
      await deleteCanonicalPerson(id, stylebookSlug)
      navigate(canonicalListHref)
    } catch (e) {
      if (isStylebookApiNotFoundError(e)) {
        navigate(canonicalListHref)
        return
      }
      console.error(e)
      showError(e instanceof Error ? e.message : "Delete failed")
    } finally {
      setDeleting(false)
      setDeleteOpen(false)
    }
  }, [id, stylebookSlug, navigate, canonicalListHref, showError])

  usePromptDeleteEmptyCanonical({
    canonicalKey: `${stylebookSlug}:${evidenceProjectSlug}:${id ?? ""}`,
    enabled: Boolean(id && !deleting),
    mentions,
    mentionsLoading,
    substrates,
    substratesLoading,
    showConfirm,
    onDelete,
  })

  const notFound = !loading && !person ? (
    <div className="container mx-auto p-6">
      <p className="text-muted-foreground">Person not found.</p>
      <Button variant="outline" className="mt-4" asChild>
        <Link to={canonicalListHref}>Back to people</Link>
      </Button>
    </div>
  ) : undefined

  return (
    <CanonicalDetailLayout
      config={personCanonicalDetailConfig}
      loading={loading}
      notFound={notFound}
      breadcrumbs={[
        { label: crumbRoot.label, to: crumbRoot.to },
        { label: personCanonicalDetailConfig.listBreadcrumbLabel, to: canonicalListHref },
        { label: person?.label ?? "" },
      ]}
      title={person?.label ?? ""}
      editing={editing}
      saving={saving}
      canEdit={canEdit}
      onStartEdit={() => {
        if (person) resetEditFieldsFromPerson(person)
        setEditing(true)
      }}
      onCancelEdit={() => {
        if (person) resetEditFieldsFromPerson(person)
        setEditing(false)
      }}
      onSave={() => void handleSave()}
      onDeleteClick={() => setDeleteOpen(true)}
      deleteOpen={deleteOpen}
      onDeleteOpenChange={(open) => !deleting && setDeleteOpen(open)}
      deleting={deleting}
      onDelete={onDelete}
      stylebookSlug={stylebookSlug}
      entityId={person?.id}
      entityDisplayName={person?.label}
      details={
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
                  <span className="text-muted-foreground">Name:</span> {person?.label}
                </div>
                {person?.title ? (
                  <div>
                    <span className="text-muted-foreground">Title:</span> {person.title}
                  </div>
                ) : null}
                {person?.affiliation ? (
                  <div>
                    <span className="text-muted-foreground">Affiliation:</span> {person.affiliation}
                  </div>
                ) : null}
                {person?.person_type ? (
                  <div>
                    <span className="text-muted-foreground">Type:</span>{" "}
                    {placeExtractTypeLabel(person.person_type)}
                  </div>
                ) : null}
                <div>
                  <span className="text-muted-foreground">Public figure:</span>{" "}
                  {person?.public_figure ? "Yes" : "No"}
                </div>
                {person?.sort_key ? (
                  <div>
                    <span className="text-muted-foreground">Sort key:</span> {person.sort_key}
                  </div>
                ) : null}
              </>
            )}
          </CardContent>
        </Card>
      }
      mentions={{
        substrates,
        mentions,
        loading: tableLoading,
        unlinkingId,
        onUnlink: (s) => void handleUnlinkSubstrate(s),
        onMove: setMoveSubstrate,
      }}
      meta={
        person && stylebookSlug ? (
          <PersonMetaTab
            personId={person.id}
            stylebookSlug={stylebookSlug}
            onMetaUpdated={() => void loadPerson(person.id, stylebookSlug, true)}
          />
        ) : null
      }
    >
      {moveSubstrate ? (
        <PersonCanonicalLinkModal
          open={moveSubstrate !== null}
          onOpenChange={(o) => {
            if (!o) setMoveSubstrate(null)
          }}
          projectSlug={moveSubstrate.project_slug}
          stylebookSlug={stylebookSlug}
          substratePersonId={moveSubstrate.id}
          excludeCanonicalId={person?.id ?? ""}
          title="Move linked person to another canonical"
          onDone={() => void refreshCanonicalPage(true)}
        />
      ) : null}
    </CanonicalDetailLayout>
  )
}
