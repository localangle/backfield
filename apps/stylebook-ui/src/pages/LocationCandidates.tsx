import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react"
import { Link, useSearchParams } from "react-router-dom"
import { useProjectCatalogScope } from "@/lib/catalogNavigation"
import { useScopeBreadcrumbRoot } from "@/lib/breadcrumbs"
import { useSelectedStylebookLabel } from "@/lib/stylebookScopeContext"
import { fetchProjects, type Project } from "@/lib/api"
import {
  acceptCandidate,
  deferCandidate,
  getCandidateContext,
  getCanonicalLocationLegacy,
  getSuggestedCanonicals,
  linkSubstrateToCanonical,
  listCandidates,
  listLocationCandidateTypes,
  updateCandidateNote,
  type Candidate,
  type CandidateContextResponse,
} from "@/lib/api"
import {
  PLACE_EXTRACT_LOCATION_TYPES,
  placeExtractTypeLabel,
  sortReviewQueueTypeFilterOptions,
} from "@/lib/place-extract-type-label"
import { pickCreateLinkNudge } from "@/lib/candidateQueueSimilarity"
import { useCandidateQueueToasts } from "@/lib/useCandidateQueueToasts"
import { useCandidateQueueInlineNote } from "@/lib/useCandidateQueueInlineNote"
import { CanonicalLinkModal } from "@/components/CanonicalLinkModal"
import { CandidateQueueCreatedToast } from "@/components/CandidateQueueCreatedToast"
import { CandidateQueueLinkedToast } from "@/components/CandidateQueueLinkedToast"
import { CandidateQueueInlineNote } from "@/components/CandidateQueueInlineNote"
import { CreateCanonicalLinkNudgeAlert } from "@/components/CreateCanonicalLinkNudgeAlert"
import { PotentialCandidateLinksDialog } from "@/components/PotentialCandidateLinksDialog"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import Pagination from "@/components/Pagination"
import { cn } from "@/lib/utils"
import { Breadcrumbs } from "@/components/Breadcrumbs"
import {
  CandidateReviewReasons,
  candidateReviewLines,
} from "@/components/CandidateReviewReasons"
import { ChevronRight, Clock, Link2, Loader2, PlusCircle, StickyNote, X } from "lucide-react"

/** Row action aligned with `canonical_suggestion.suggested_action` from the API. */
function suggestedRowAction(c: Candidate): "link" | "create_new" | "defer" | null {
  const raw = c.canonical_suggestion?.suggested_action
  if (raw === "link_existing") return "link"
  if (raw === "materialize_new") return "create_new"
  if (raw === "defer") return "defer"
  return null
}

function suggestedActionShortLabel(c: Candidate): string | null {
  const sug = suggestedRowAction(c)
  if (sug === "link") return "Link to existing canonical"
  if (sug === "create_new") return "Create new canonical"
  if (sug === "defer") return "Defer (remove from linking queue)"
  return null
}

const REVIEW_QUEUE_PAGE_SIZE = 100

export default function LocationCandidates() {
  const {
    projectScopeSlug,
    workflowScopeSuffix,
    stylebookSlug,
    catalogBasePath,
    filterScopeSuffix,
  } = useProjectCatalogScope()
  const crumbRoot = useScopeBreadcrumbRoot()
  const stylebookLabel = useSelectedStylebookLabel()
  const [searchParams, setSearchParams] = useSearchParams()
  const projectSlug = projectScopeSlug
  const [projects, setProjects] = useState<Project[]>([])
  const [projectsLoading, setProjectsLoading] = useState(true)
  const projectDisplayName = useMemo(() => {
    const row = projects.find((p) => p.slug === projectSlug)
    const name = row?.name?.trim()
    return name || projectSlug || "this project"
  }, [projects, projectSlug])
  const [loading, setLoading] = useState(false)
  const [listTotal, setListTotal] = useState(0)
  const [listPage, setListPage] = useState(1)
  const [listHasNext, setListHasNext] = useState(false)
  const [listHasPrev, setListHasPrev] = useState(false)
  /** Bumps when `filterKey` changes so list fetch resets to page 1 without a stale `listPage` fetch. */
  const [listFetchGen, setListFetchGen] = useState(0)
  const filterKeySeenRef = useRef<string | null>(null)
  const [candidates, setCandidates] = useState<Candidate[]>([])
  const [status, setStatus] = useState<"open" | "deferred">("open")
  const [query, setQuery] = useState("")
  const [debouncedQuery, setDebouncedQuery] = useState("")
  const [typeFilter, setTypeFilter] = useState<string>("all")
  const filterKey = useMemo(
    () => `${projectSlug}|${stylebookSlug}|${status}|${debouncedQuery}|${typeFilter}`,
    [projectSlug, stylebookSlug, status, debouncedQuery, typeFilter],
  )
  const [types, setTypes] = useState<string[]>([])
  const [acceptingId, setAcceptingId] = useState<number | null>(null)
  const [deferringId, setDeferringId] = useState<number | null>(null)
  const [linkModalId, setLinkModalId] = useState<number | null>(null)
  const [linkModalInitialCanonicalId, setLinkModalInitialCanonicalId] = useState<string | null>(
    null,
  )
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [contextById, setContextById] = useState<Record<number, CandidateContextResponse>>({})
  const [contextLoadingId, setContextLoadingId] = useState<number | null>(null)
  const [createModalId, setCreateModalId] = useState<number | null>(null)
  const [createCanonicalDraft, setCreateCanonicalDraft] = useState("")
  const [createModalLocationType, setCreateModalLocationType] = useState("")
  const [error, setError] = useState<string | null>(null)

  const [createLinkNudge, setCreateLinkNudge] = useState<{
    canonicalId: string
    label: string
  } | null>(null)
  const [linkingSuggestedId, setLinkingSuggestedId] = useState<number | null>(null)

  useEffect(() => {
    let cancelled = false
    setProjectsLoading(true)
    void fetchProjects()
      .then((rows) => {
        if (cancelled) return
        setProjects(rows)
      })
      .catch((e) => {
        console.error("Failed to fetch projects:", e)
        if (!cancelled) setProjects([])
      })
      .finally(() => {
        if (!cancelled) setProjectsLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const createModalCandidate = useMemo(
    () => (createModalId === null ? undefined : candidates.find((x) => x.id === createModalId)),
    [candidates, createModalId]
  )

  const orderedTypeFilterOptions = useMemo(
    () => sortReviewQueueTypeFilterOptions(types),
    [types],
  )

  const createModalTypeOptions = useMemo(
    () => sortReviewQueueTypeFilterOptions([...PLACE_EXTRACT_LOCATION_TYPES]),
    [],
  )

  const listTotalPages = useMemo(
    () => Math.max(1, Math.ceil(listTotal / REVIEW_QUEUE_PAGE_SIZE)),
    [listTotal],
  )

  /** When filters change, reset to page 1 and bump generation so the list fetch does not use a stale page. */
  useEffect(() => {
    if (!projectSlug) {
      filterKeySeenRef.current = null
      return
    }
    if (filterKeySeenRef.current === null) {
      filterKeySeenRef.current = filterKey
      return
    }
    if (filterKeySeenRef.current === filterKey) return
    filterKeySeenRef.current = filterKey
    setListFetchGen((g) => g + 1)
    setListPage(1)
  }, [filterKey, projectSlug])

  useEffect(() => {
    const t = window.setTimeout(() => setDebouncedQuery(query), 250)
    return () => window.clearTimeout(t)
  }, [query])

  function setQueryImmediate(next: string) {
    setQuery(next)
    setDebouncedQuery(next)
  }

  const refreshCreateLinkNudge = useCallback(
    async (substrateLocationId: number, draftLabel: string) => {
      if (!projectSlug) return
      const draft = draftLabel.trim()
      if (!draft) {
        setCreateLinkNudge(null)
        return
      }
      try {
        const res = await getSuggestedCanonicals(projectSlug, substrateLocationId, 16)
        const nudge = pickCreateLinkNudge(res.suggestions, draft)
        setCreateLinkNudge(
          nudge ? { canonicalId: nudge.canonicalId, label: nudge.label } : null,
        )
      } catch {
        setCreateLinkNudge(null)
      }
    },
    [projectSlug],
  )

  useEffect(() => {
    if (!projectSlug) return
    void (async () => {
      try {
        const res = await listLocationCandidateTypes(projectSlug, status)
        setTypes(res.types)
      } catch {
        setTypes([])
      }
    })()
  }, [projectSlug, status])

  useEffect(() => {
    if (createModalId === null || !projectSlug) return
    let cancelled = false
    const draft = createCanonicalDraft.trim()
    if (!draft) {
      setCreateLinkNudge(null)
      return
    }
    // Do not show a loading banner; only surface UI when a similar canonical is found.
    setCreateLinkNudge(null)
    const t = window.setTimeout(() => {
      void (async () => {
        if (!cancelled) await refreshCreateLinkNudge(createModalId, draft)
      })()
    }, 280)
    return () => {
      cancelled = true
      window.clearTimeout(t)
    }
  }, [createModalId, createCanonicalDraft, projectSlug, refreshCreateLinkNudge])

  /** Re-fetch the queue after an action (link, create, defer, save note) without the full-page loading state. */
  const refreshListQuiet = useCallback(async () => {
    if (!projectSlug) return
    setError(null)
    const type_filter = typeFilter === "all" ? undefined : typeFilter
    const q = debouncedQuery.trim() || undefined
    const offset = (listPage - 1) * REVIEW_QUEUE_PAGE_SIZE
    try {
      const res = await listCandidates(projectSlug, status, false, {
        limit: REVIEW_QUEUE_PAGE_SIZE,
        offset,
        type_filter,
        q,
      })
      setListTotal(res.total)
      setCandidates(res.candidates)
      setListHasNext(res.has_next)
      setListHasPrev(res.has_prev)
      if (
        res.candidates.length === 0 &&
        res.total > 0 &&
        offset >= REVIEW_QUEUE_PAGE_SIZE
      ) {
        setListPage((p) => Math.max(1, p - 1))
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request failed")
    }
  }, [projectSlug, status, debouncedQuery, typeFilter, listPage])

  const fetchOpenLocationCandidatesForLabel = useCallback(
    async (label: string) => {
      if (!projectSlug) return []
      const res = await listCandidates(projectSlug, "open", false, {
        limit: 100,
        offset: 0,
        q: label,
      })
      return res.candidates
    },
    [projectSlug],
  )

  const queueToasts = useCandidateQueueToasts<Candidate>({
    projectSlug,
    fetchOpenCandidatesForLabel: fetchOpenLocationCandidatesForLabel,
    getCandidateLabel: (c) => c.suggested_name ?? "",
    mapFollowupRow: (c) => ({
      rowKey: c.id,
      location: c.suggested_name || "—",
      typeLabel: c.suggested_type ? placeExtractTypeLabel(c.suggested_type) : "—",
      address: c.suggested_formatted_address || "—",
    }),
    linkCandidateToCanonical: async (c, canonicalId) => {
      if (!projectSlug) return
      await linkSubstrateToCanonical(c.id, projectSlug, canonicalId)
    },
    onAfterToastLink: refreshListQuiet,
  })

  const saveCandidateNote = useCallback(
    async (candidateId: number, note: string | null) => {
      if (!projectSlug) return
      setError(null)
      try {
        await updateCandidateNote(projectSlug, candidateId, note)
        setContextById((prev) => {
          const existing = prev[candidateId]
          if (!existing) return prev
          return { ...prev, [candidateId]: { ...existing, note } }
        })
        await refreshListQuiet()
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to save note")
      }
    },
    [projectSlug, refreshListQuiet],
  )

  const candidateNotes = useCandidateQueueInlineNote({ onSave: saveCandidateNote })

  // Initial + filter/pagination changes. `listFetchGen` bumps when filters change so we never fetch
  // a stale page with new filters (see filterKey effect above).
  useEffect(() => {
    if (!projectSlug) return
    let cancelled = false
    void (async () => {
      setLoading(true)
      setError(null)
      const type_filter = typeFilter === "all" ? undefined : typeFilter
      const q = debouncedQuery.trim() || undefined
      const offset = (listPage - 1) * REVIEW_QUEUE_PAGE_SIZE
      try {
        const res = await listCandidates(projectSlug, status, false, {
          limit: REVIEW_QUEUE_PAGE_SIZE,
          offset,
          type_filter,
          q,
        })
        if (cancelled) return
        setListTotal(res.total)
        setCandidates(res.candidates)
        setListHasNext(res.has_next)
        setListHasPrev(res.has_prev)
        if (
          !cancelled &&
          res.candidates.length === 0 &&
          res.total > 0 &&
          offset >= REVIEW_QUEUE_PAGE_SIZE
        ) {
          setListPage((p) => Math.max(1, p - 1))
        }
      } catch (e) {
        if (cancelled) return
        setError(e instanceof Error ? e.message : "Request failed")
        setListTotal(0)
        setCandidates([])
        setListHasNext(false)
        setListHasPrev(false)
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [projectSlug, status, debouncedQuery, typeFilter, listPage, listFetchGen])

  function defaultNewCanonicalLabel(c: Candidate): string {
    const fromName = (c.suggested_name ?? "").trim()
    if (fromName) return fromName
    return (c.suggested_formatted_address ?? "").trim()
  }

  function defaultNewCanonicalLocationType(c: Candidate): string {
    const t = (c.suggested_type ?? "").trim().toLowerCase()
    if (t && (PLACE_EXTRACT_LOCATION_TYPES as readonly string[]).includes(t)) return t
    return "place"
  }

  function openCreateCanonicalModal(c: Candidate) {
    setCreateModalId(c.id)
    setCreateCanonicalDraft(defaultNewCanonicalLabel(c))
    setCreateModalLocationType(defaultNewCanonicalLocationType(c))
    setCreateLinkNudge(null)
  }

  function closeCreateCanonicalModal() {
    setCreateModalId(null)
    setCreateCanonicalDraft("")
    setCreateModalLocationType("")
    setCreateLinkNudge(null)
  }

  async function submitCreateCanonicalFromModal() {
    if (!projectSlug || createModalId === null) return
    const name = createCanonicalDraft.trim()
    if (!name) {
      setError("Enter a label for the new canonical.")
      return
    }
    const location_type = createModalLocationType.trim().toLowerCase()
    if (!location_type || !(PLACE_EXTRACT_LOCATION_TYPES as readonly string[]).includes(location_type)) {
      setError("Select a valid location type.")
      return
    }
    setAcceptingId(createModalId)
    setError(null)
    try {
      const acceptRes = await acceptCandidate(projectSlug, createModalId, {
        create_new: true,
        name,
        location_type,
      })
      await refreshListQuiet()
      closeCreateCanonicalModal()
      const cid = acceptRes.stylebook_location_canonical_id
      if (typeof cid !== "string" || !cid.trim()) {
        setError(
          "Canonical was created, but the server did not return its id. Reload the page if you need to link similar candidates from the toast.",
        )
        return
      }
      queueToasts.created.show({ canonicalLabel: name, canonicalId: cid })
    } catch (e) {
      setError(e instanceof Error ? e.message : "Accept failed")
    } finally {
      setAcceptingId(null)
    }
  }

  async function linkCandidateToSuggestedCanonical(c: Candidate) {
    if (!projectSlug) return
    const cid = (c.canonical_suggestion?.stylebook_location_canonical_id ?? "").trim()
    if (!cid) return
    setLinkingSuggestedId(c.id)
    setError(null)
    try {
      await linkSubstrateToCanonical(c.id, projectSlug, cid)
      let canonLabel = cid
      try {
        const canon = await getCanonicalLocationLegacy(cid, projectSlug)
        canonLabel = (canon.label ?? "").trim() || cid
      } catch {
        // ignore; fall back to id
      }
      queueToasts.linked.show({
        canonicalId: cid,
        canonicalLabel: canonLabel,
        candidateLabel: (c.suggested_name ?? "").trim() || `Location ${c.id}`,
      })
      await refreshListQuiet()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Link failed")
    } finally {
      setLinkingSuggestedId(null)
    }
  }

  async function handleDefer(c: Candidate) {
    if (!projectSlug) return
    setDeferringId(c.id)
    setError(null)
    try {
      await deferCandidate(projectSlug, c.id)
      await refreshListQuiet()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Defer failed")
    } finally {
      setDeferringId(null)
    }
  }

  async function toggleExpanded(c: Candidate) {
    if (!projectSlug) return
    const next = expandedId === c.id ? null : c.id
    setExpandedId(next)
    if (next === null) return
    if (contextById[next]) return
    setContextLoadingId(next)
    try {
      const ctx = await getCandidateContext(projectSlug, next, 3)
      setContextById((prev) => ({ ...prev, [next]: ctx }))
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load context")
    } finally {
      setContextLoadingId(null)
    }
  }

  return (
    <div className="container mx-auto p-6 space-y-6">
      {queueToasts.created.isVisible && queueToasts.created.payload ? (
        <CandidateQueueCreatedToast
          title="Canonical created"
          canonicalHref={`${catalogBasePath}/locations/canonical/${queueToasts.created.payload.canonicalId}${filterScopeSuffix}`}
          canonicalLabel={queueToasts.created.payload.canonicalLabel}
          leaving={queueToasts.created.leaving}
          followupCheckingMessage="Checking the open queue for related locations…"
          followupLoading={queueToasts.followup.loading}
          followupError={queueToasts.followup.error}
          hasPotentialLinks={queueToasts.followup.hasMatches}
          onOpenPotentialLinks={queueToasts.followup.openPotentialLinks}
          onDismiss={queueToasts.created.dismissNow}
        />
      ) : null}
      {queueToasts.linked.isVisible && queueToasts.linked.payload ? (
        <CandidateQueueLinkedToast
          title="Linked to canonical"
          candidateLabel={queueToasts.linked.payload.candidateLabel}
          canonicalHref={`${catalogBasePath}/locations/canonical/${queueToasts.linked.payload.canonicalId}${filterScopeSuffix}`}
          canonicalLabel={queueToasts.linked.payload.canonicalLabel}
          leaving={queueToasts.linked.leaving}
          onDismiss={queueToasts.linked.dismissNow}
        />
      ) : null}
      <div className="flex justify-between items-center">
        <div className="min-w-0">
          <Breadcrumbs
            className="mb-3"
            items={[
              { label: crumbRoot.label, to: crumbRoot.to },
              { label: "Locations", to: `${catalogBasePath}/locations/canonical${filterScopeSuffix}` },
              { label: "Candidates" },
            ]}
          />
          <h1 className="text-3xl font-bold">Location candidates</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Link candidates from{" "}
            <span className="font-semibold text-foreground">{projectDisplayName}</span> to Stylebook{" "}
            <span className="font-semibold text-foreground">{stylebookLabel}</span>
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="hidden sm:flex items-center gap-2">
            <Label className="text-sm text-muted-foreground">Project</Label>
            <Select
              value={projectSlug}
              onValueChange={(slug) => {
                setSearchParams((prev) => {
                  const next = new URLSearchParams(prev)
                  next.set("project_scope", slug)
                  return next
                })
              }}
              disabled={projectsLoading || projects.length === 0}
            >
              <SelectTrigger className="w-[16rem]">
                <SelectValue placeholder={projectsLoading ? "Loading…" : "Choose a project"} />
              </SelectTrigger>
              <SelectContent>
                {projects.map((p) => (
                  <SelectItem key={p.id} value={p.slug}>
                    {p.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Link to={`${catalogBasePath}/locations/canonical${filterScopeSuffix}`}>
            <Button variant="outline">Canonical locations</Button>
          </Link>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Review queue</CardTitle>
          <CardDescription>
            Unlinked locations for this project. Use “Link” to attach to an existing canonical, or
            “Create new” to add a new one.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="candidate-search">Search</Label>
            <Input
              id="candidate-search"
              className="w-full max-w-none"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search name…"
            />
          </div>
          <div className="flex flex-wrap gap-4 items-end justify-between">
            <div className="w-full max-w-xs">
              <Label>Type</Label>
              <Select value={typeFilter} onValueChange={setTypeFilter}>
                <SelectTrigger>
                  <SelectValue placeholder="All types" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All</SelectItem>
                  {orderedTypeFilterOptions.map((t) => (
                    <SelectItem key={t} value={t}>
                      {placeExtractTypeLabel(t)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {loading && (
              <div className="flex items-center gap-2 text-sm text-muted-foreground pb-2">
                <Loader2 className="h-4 w-4 animate-spin shrink-0" />
                <span>Loading…</span>
              </div>
            )}
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <div className="overflow-hidden rounded-md border">
            <div
              className="flex gap-8 border-b border-border bg-muted/20 px-4"
              role="tablist"
              aria-label="Review queue"
            >
              <button
                type="button"
                role="tab"
                aria-selected={status === "open"}
                disabled={loading}
                className={cn(
                  "whitespace-nowrap border-b-2 -mb-px py-3 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:opacity-50",
                  status === "open"
                    ? "border-primary text-foreground"
                    : "border-transparent text-muted-foreground hover:text-foreground"
                )}
                onClick={() => setStatus("open")}
              >
                For review
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={status === "deferred"}
                disabled={loading}
                className={cn(
                  "whitespace-nowrap border-b-2 -mb-px py-3 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:opacity-50",
                  status === "deferred"
                    ? "border-primary text-foreground"
                    : "border-transparent text-muted-foreground hover:text-foreground"
                )}
                onClick={() => setStatus("deferred")}
              >
                Deferred
              </button>
            </div>
            <Table className="table-fixed">
              <colgroup>
                <col style={{ width: "27%" }} />
                <col style={{ width: "12%" }} />
                <col style={{ width: "27%" }} />
                <col style={{ width: "10%" }} />
                {/* Four icon buttons, gaps, cell padding, and focus rings need a firm minimum. */}
                <col style={{ width: "13rem" }} />
              </colgroup>
              <TableHeader>
                <TableRow>
                  <TableHead className="min-w-0">Location</TableHead>
                  <TableHead className="min-w-0 overflow-hidden">
                    <span className="block truncate">Type</span>
                  </TableHead>
                  <TableHead className="min-w-0">Address</TableHead>
                  <TableHead className="whitespace-nowrap">Created</TableHead>
                  <TableHead className="min-w-0 text-right">
                    <span className="sr-only">Actions</span>
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {candidates.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={5} className="text-muted-foreground">
                      No unlinked locations.
                    </TableCell>
                  </TableRow>
                ) : (
                  candidates.map((c) => {
                    const savedNoteText = String(contextById[c.id]?.note ?? c.note ?? "").trim()
                    const rowSug = suggestedRowAction(c)
                    const rowSugLabel = suggestedActionShortLabel(c)
                    const suggestedCanonicalId =
                      rowSug === "link" &&
                      c.canonical_suggestion?.stylebook_location_canonical_id != null
                        ? String(c.canonical_suggestion.stylebook_location_canonical_id).trim()
                        : ""
                    const typeLabel = c.suggested_type
                      ? placeExtractTypeLabel(c.suggested_type)
                      : "—"
                    return (
                    <Fragment key={c.id}>
                      <TableRow id={`candidate-row-${c.id}`}>
                        <TableCell className="font-medium min-w-0">
                          <div className="flex flex-col items-start gap-1 min-w-0">
                          <div className="flex items-center gap-2 min-w-0">
                            <Button
                              type="button"
                              size="icon"
                              variant="ghost"
                              className="h-8 w-8 shrink-0 text-muted-foreground hover:text-foreground"
                              onClick={() => void toggleExpanded(c)}
                              disabled={contextLoadingId === c.id}
                              aria-expanded={expandedId === c.id}
                              aria-label={expandedId === c.id ? "Hide context" : "Show context"}
                            >
                              {contextLoadingId === c.id ? (
                                <Loader2 className="h-4 w-4 animate-spin" />
                              ) : (
                                <ChevronRight
                                  className={cn(
                                    "h-4 w-4 transition-transform duration-200",
                                    expandedId === c.id && "rotate-90"
                                  )}
                                  aria-hidden
                                />
                              )}
                            </Button>
                            <span className="min-w-0 break-words">{c.suggested_name || "—"}</span>
                            {c.note ? (
                              <StickyNote
                                className="h-3.5 w-3.5 shrink-0 text-muted-foreground"
                                aria-label="Has a note"
                              />
                            ) : null}
                          </div>
                          {rowSugLabel ? (
                            <div className="flex flex-wrap items-center gap-2 pl-10">
                              <Badge variant="secondary" className="font-normal">
                                Suggested
                              </Badge>
                              <span className="text-xs text-muted-foreground">{rowSugLabel}</span>
                            </div>
                          ) : null}
                          <CandidateReviewReasons lines={candidateReviewLines(c)} />
                          </div>
                        </TableCell>
                        <TableCell className="min-w-0 overflow-hidden align-top">
                          <span
                            className="block truncate"
                            title={typeLabel !== "—" ? typeLabel : undefined}
                          >
                            {typeLabel}
                          </span>
                        </TableCell>
                        <TableCell className="min-w-0 max-w-xs truncate">
                          {c.suggested_formatted_address || "—"}
                        </TableCell>
                        <TableCell className="text-muted-foreground text-sm whitespace-nowrap">
                          {c.created_at ? new Date(c.created_at).toLocaleDateString() : "—"}
                        </TableCell>
                        <TableCell className="text-right whitespace-nowrap align-top overflow-visible">
                          <div className="inline-flex flex-nowrap items-center justify-end gap-1.5 px-0.5">
                            <Button
                              type="button"
                              size="icon"
                              variant={rowSug === "link" ? "default" : "outline"}
                              className={cn(
                                "h-8 w-8 shrink-0",
                                rowSug === "link" &&
                                  "ring-2 ring-primary ring-offset-2 ring-offset-background shadow-sm",
                              )}
                              title={
                                rowSug === "link" && suggestedCanonicalId
                                  ? "Suggested: link now"
                                  : rowSug === "link"
                                    ? "Suggested: link to existing canonical"
                                    : "Link to existing canonical"
                              }
                              aria-label={
                                rowSug === "link" && suggestedCanonicalId
                                  ? "Link to suggested canonical"
                                  : "Link to existing canonical"
                              }
                              disabled={
                                acceptingId === c.id ||
                                deferringId === c.id ||
                                linkingSuggestedId === c.id
                              }
                              onClick={() => {
                                if (rowSug === "link" && suggestedCanonicalId) {
                                  void linkCandidateToSuggestedCanonical(c)
                                  return
                                }
                                setLinkModalId(c.id)
                                setLinkModalInitialCanonicalId(null)
                              }}
                            >
                              {linkingSuggestedId === c.id ? (
                                <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                              ) : (
                                <Link2 className="h-4 w-4" aria-hidden />
                              )}
                            </Button>
                            <Button
                              type="button"
                              size="icon"
                              variant={rowSug === "create_new" ? "default" : "secondary"}
                              className={cn(
                                "h-8 w-8 shrink-0",
                                rowSug === "create_new" &&
                                  "ring-2 ring-primary ring-offset-2 ring-offset-background shadow-sm",
                              )}
                              title={
                                rowSug === "create_new"
                                  ? "Suggested: create new canonical from this place"
                                  : "Create new canonical from this place"
                              }
                              aria-label={
                                acceptingId === c.id ? "Creating canonical" : "Create new canonical"
                              }
                              disabled={acceptingId === c.id || deferringId === c.id}
                              onClick={() => openCreateCanonicalModal(c)}
                            >
                              {acceptingId === c.id ? (
                                <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                              ) : (
                                <PlusCircle className="h-4 w-4" aria-hidden />
                              )}
                            </Button>
                            {status === "open" && (
                              <Button
                                type="button"
                                size="icon"
                                variant={rowSug === "defer" ? "default" : "outline"}
                                className={cn(
                                  "h-8 w-8 shrink-0",
                                  rowSug === "defer" &&
                                    "ring-2 ring-primary ring-offset-2 ring-offset-background shadow-sm",
                                )}
                                title={
                                  rowSug === "defer"
                                    ? "Suggested: defer (remove from linking queue)"
                                    : "Defer — remove from linking queue"
                                }
                                aria-label="Defer — remove from linking queue"
                                disabled={acceptingId === c.id || deferringId === c.id}
                                onClick={() => void handleDefer(c)}
                              >
                                {deferringId === c.id ? (
                                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                                ) : (
                                  <Clock className="h-4 w-4" aria-hidden />
                                )}
                              </Button>
                            )}
                          </div>
                        </TableCell>
                      </TableRow>
                      {expandedId === c.id && (
                        <TableRow>
                          <TableCell colSpan={5} className="bg-muted/30 min-w-0">
                            <div className="space-y-3 py-2 break-words [overflow-wrap:anywhere]">
                              <div>
                                <div className="text-sm font-medium">Context</div>
                                {contextLoadingId === c.id ? (
                                  <div className="text-sm text-muted-foreground flex items-center gap-2 py-2">
                                    <Loader2 className="h-4 w-4 animate-spin" />
                                    Loading…
                                  </div>
                                ) : (contextById[c.id]?.examples?.length ?? 0) === 0 ? (
                                  <div className="text-sm text-muted-foreground py-1">
                                    No article examples found.
                                  </div>
                                ) : (
                                  <ul className="mt-1 space-y-1">
                                    {contextById[c.id].examples.map((ex) => (
                                      <li key={ex.article_id} className="text-sm">
                                        <span className="text-muted-foreground">
                                          {ex.article_headline ?? `Article ${ex.article_id}`}:
                                        </span>{" "}
                                        <span>{ex.text}</span>
                                      </li>
                                    ))}
                                  </ul>
                                )}
                              </div>
                              <CandidateQueueInlineNote
                                candidateId={c.id}
                                savedNoteText={savedNoteText}
                                isEditing={candidateNotes.noteEditingId === c.id}
                                draft={candidateNotes.noteDraftById[c.id] ?? ""}
                                saving={candidateNotes.noteSavingId === c.id}
                                disabled={
                                  acceptingId === c.id ||
                                  deferringId === c.id ||
                                  linkingSuggestedId === c.id
                                }
                                onOpenEditor={() =>
                                  candidateNotes.openInlineNoteEditor(c.id, savedNoteText)
                                }
                                onDraftChange={(value) =>
                                  candidateNotes.setNoteDraftById((prev) => ({
                                    ...prev,
                                    [c.id]: value,
                                  }))
                                }
                                onSave={() => void candidateNotes.saveInlineNote(c.id)}
                                onCancelEdit={() => candidateNotes.setNoteEditingId(null)}
                              />
                            </div>
                          </TableCell>
                        </TableRow>
                      )}
                    </Fragment>
                    )
                  })
                )}
              </TableBody>
            </Table>
          </div>
          <Pagination
            page={listPage}
            perPage={REVIEW_QUEUE_PAGE_SIZE}
            total={listTotal}
            totalPages={listTotalPages}
            hasNext={listHasNext}
            hasPrev={listHasPrev}
            onPageChange={setListPage}
            className="pt-4"
            itemLabel="candidates"
          />
        </CardContent>
      </Card>

      <CanonicalLinkModal
        open={linkModalId !== null}
        onOpenChange={(o) => {
          if (!o) {
            setLinkModalId(null)
            setLinkModalInitialCanonicalId(null)
          }
        }}
        projectSlug={projectSlug}
        substrateLocationId={linkModalId}
        initialCanonicalId={linkModalInitialCanonicalId}
        title="Link candidate to canonical"
        onLinked={({ id, label }) => {
          queueToasts.linked.show({
            canonicalId: id,
            canonicalLabel: label,
            candidateLabel:
              (candidates.find((c) => c.id === linkModalId)?.suggested_name ?? "").trim() ||
              (linkModalId != null ? `Location ${linkModalId}` : "Location"),
          })
        }}
        onDone={() => void refreshListQuiet()}
      />

      <Dialog
        open={createModalId !== null}
        onOpenChange={(open) => {
          if (!open && acceptingId === createModalId) return
          if (!open) closeCreateCanonicalModal()
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Create new canonical</DialogTitle>
            <DialogDescription>
              Create new canonical object in{" "}
              <span className="font-semibold text-foreground">{stylebookLabel}</span>
            </DialogDescription>
          </DialogHeader>
          {createLinkNudge ? (
            <CreateCanonicalLinkNudgeAlert
              existingLabel={createLinkNudge.label}
              entityNoun="canonical"
              disabled={createModalId === null}
              onOpenLinkFlow={() => {
                if (createModalId === null) return
                setLinkModalId(createModalId)
                setLinkModalInitialCanonicalId(createLinkNudge.canonicalId)
                closeCreateCanonicalModal()
              }}
            />
          ) : null}
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="create-canonical-type">Location type</Label>
              <Select value={createModalLocationType} onValueChange={setCreateModalLocationType}>
                <SelectTrigger id="create-canonical-type">
                  <SelectValue placeholder="Select type" />
                </SelectTrigger>
                <SelectContent>
                  {createModalTypeOptions.map((t) => (
                    <SelectItem key={t} value={t}>
                      {placeExtractTypeLabel(t)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="create-canonical-name">Canonical label</Label>
              <Input
                id="create-canonical-name"
                value={createCanonicalDraft}
                onChange={(e) => setCreateCanonicalDraft(e.target.value)}
                placeholder="e.g. Dolton, IL"
                autoFocus
              />
            </div>
            {createModalCandidate?.suggested_formatted_address ? (
              <p className="text-xs text-muted-foreground">
                Geocoded address: {createModalCandidate.suggested_formatted_address}
              </p>
            ) : null}
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              disabled={acceptingId === createModalId}
              onClick={() => closeCreateCanonicalModal()}
            >
              Cancel
            </Button>
            <Button
              type="button"
              disabled={
                acceptingId === createModalId ||
                !createCanonicalDraft.trim() ||
                !createModalLocationType.trim()
              }
              onClick={() => void submitCreateCanonicalFromModal()}
            >
              {acceptingId === createModalId ? "Creating…" : "Create canonical"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <PotentialCandidateLinksDialog
        {...queueToasts.potentialLinksDialog}
        candidateNounPlural="locations"
        linkActionLabel="Link this candidate to the new canonical"
        primaryColumnLabel="Location"
      />
    </div>
  )
}
