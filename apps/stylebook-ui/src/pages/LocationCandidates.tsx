import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react"
import { Link, useSearchParams } from "react-router-dom"
import {
  acceptCandidate,
  deferCandidate,
  getCandidateContext,
  getSuggestedCanonicals,
  linkSubstrateToCanonical,
  listCandidates,
  listLocationCandidateTypes,
  updateCandidateNote,
  type Candidate,
  type CandidateContextResponse,
} from "@/lib/api"
import { placeExtractTypeLabel, sortReviewQueueTypeFilterOptions } from "@/lib/place-extract-type-label"
import { CanonicalLinkModal } from "@/components/CanonicalLinkModal"
import { Button } from "@/components/ui/button"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
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
import { Textarea } from "@/components/ui/textarea"
import Pagination from "@/components/Pagination"
import { cn } from "@/lib/utils"
import {
  CheckCircle2,
  ChevronRight,
  Clock,
  Link2,
  Loader2,
  PlusCircle,
  StickyNote,
  X,
} from "lucide-react"

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

function normalizeLabelForCompare(s: string): string {
  return s.trim().toLowerCase().replace(/\s+/g, " ")
}

function diceBigramCoefficient(a: string, b: string): number {
  if (a.length < 2 || b.length < 2) return 0
  const bigrams = (s: string) => {
    const arr: string[] = []
    for (let i = 0; i < s.length - 1; i++) arr.push(s.slice(i, i + 2))
    return arr
  }
  const A = bigrams(a)
  const B = bigrams(b)
  const counts = new Map<string, number>()
  for (const g of A) counts.set(g, (counts.get(g) ?? 0) + 1)
  let inter = 0
  for (const g of B) {
    const n = counts.get(g) ?? 0
    if (n > 0) {
      inter++
      counts.set(g, n - 1)
    }
  }
  return (2 * inter) / (A.length + B.length)
}

/** 0–1 similarity for comparing a draft canonical label to an existing canonical label. */
function stringSimilarityForLabels(draft: string, candidateLabel: string): number {
  const d = normalizeLabelForCompare(draft)
  const c = normalizeLabelForCompare(candidateLabel)
  if (!d || !c) return 0
  if (d === c) return 1
  if (d.includes(c) || c.includes(d)) return 0.93
  return diceBigramCoefficient(d, c)
}

/** Higher = closer text match between a queue row name and the search needle. */
function similarityRankScoreForCandidate(c: Candidate, needleRaw: string): number {
  const name = normalizeLabelForCompare(c.suggested_name ?? "")
  const needle = normalizeLabelForCompare(needleRaw)
  if (!name || !needle) return 0
  if (name === needle) return 1_000_000
  if (name.startsWith(needle) || needle.startsWith(name)) return 500_000
  if (name.includes(needle) || needle.includes(name)) return 200_000
  const ta = new Set(name.split(/[\s,]+/).filter(Boolean))
  const tb = new Set(needle.split(/[\s,]+/).filter(Boolean))
  let inter = 0
  for (const t of ta) if (tb.has(t)) inter++
  const union = ta.size + tb.size - inter
  const jaccard = union === 0 ? 0 : inter / union
  return jaccard * 10_000 + diceBigramCoefficient(name, needle) * 1000
}

const REVIEW_QUEUE_PAGE_SIZE = 100

function rankSimilarCandidates(rows: Candidate[], needle: string): Candidate[] {
  const scored = rows.map((c) => ({
    c,
    s: similarityRankScoreForCandidate(c, needle),
  }))
  scored.sort((a, b) => {
    if (b.s !== a.s) return b.s - a.s
    const an = (a.c.suggested_name ?? "").toLowerCase()
    const bn = (b.c.suggested_name ?? "").toLowerCase()
    return an.localeCompare(bn)
  })
  return scored.map((x) => x.c)
}

export default function LocationCandidates() {
  const [searchParams] = useSearchParams()
  const projectSlug = searchParams.get("project") || ""
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
    () => `${projectSlug}|${status}|${debouncedQuery}|${typeFilter}`,
    [projectSlug, status, debouncedQuery, typeFilter],
  )
  const [types, setTypes] = useState<string[]>([])
  const [acceptingId, setAcceptingId] = useState<number | null>(null)
  const [deferringId, setDeferringId] = useState<number | null>(null)
  const [linkModalId, setLinkModalId] = useState<number | null>(null)
  const [linkModalInitialCanonicalId, setLinkModalInitialCanonicalId] = useState<number | null>(
    null
  )
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [contextById, setContextById] = useState<Record<number, CandidateContextResponse>>({})
  const [contextLoadingId, setContextLoadingId] = useState<number | null>(null)
  const [noteModalId, setNoteModalId] = useState<number | null>(null)
  const [noteModalDraft, setNoteModalDraft] = useState("")
  const [noteSavingId, setNoteSavingId] = useState<number | null>(null)
  const [createModalId, setCreateModalId] = useState<number | null>(null)
  const [createCanonicalDraft, setCreateCanonicalDraft] = useState("")
  const [error, setError] = useState<string | null>(null)

  const [createdToast, setCreatedToast] = useState<{
    canonicalLabel: string
    canonicalId: number
  } | null>(null)
  /** Same query as “show similar candidates”: open queue + q + limit 100, ranked top 5. */
  const [toastFollowupLoading, setToastFollowupLoading] = useState(false)
  const [toastFollowupError, setToastFollowupError] = useState<string | null>(null)
  const [toastFollowupRows, setToastFollowupRows] = useState<Candidate[]>([])
  const [potentialLinksOpen, setPotentialLinksOpen] = useState(false)
  const [toastLinkBusyId, setToastLinkBusyId] = useState<number | null>(null)
  const [toastLinkError, setToastLinkError] = useState<string | null>(null)
  const [createLinkNudge, setCreateLinkNudge] = useState<{
    canonicalId: number
    label: string
  } | null>(null)

  const noteModalCandidate = useMemo(
    () => (noteModalId === null ? undefined : candidates.find((x) => x.id === noteModalId)),
    [candidates, noteModalId]
  )

  const createModalCandidate = useMemo(
    () => (createModalId === null ? undefined : candidates.find((x) => x.id === createModalId)),
    [candidates, createModalId]
  )

  const orderedTypeFilterOptions = useMemo(
    () => sortReviewQueueTypeFilterOptions(types),
    [types],
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
        let best: { canonicalId: number; label: string; score: number } | null = null
        for (const s of res.suggestions) {
          const score = stringSimilarityForLabels(draft, s.label)
          if (!best || score > best.score) {
            best = { canonicalId: s.canonical_id, label: s.label, score }
          }
        }
        if (best && best.score >= 0.86) {
          setCreateLinkNudge({ canonicalId: best.canonicalId, label: best.label })
        } else {
          setCreateLinkNudge(null)
        }
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

  const prefetchToastFollowupCandidates = useCallback(async () => {
    const label = createdToast?.canonicalLabel?.trim()
    if (!projectSlug || !label) return
    setToastFollowupLoading(true)
    setToastFollowupError(null)
    try {
      const res = await listCandidates(projectSlug, "open", false, {
        limit: 100,
        offset: 0,
        q: label,
      })
      const ranked = rankSimilarCandidates(res.candidates, label).slice(0, 5)
      setToastFollowupRows(ranked)
    } catch (e) {
      setToastFollowupError(e instanceof Error ? e.message : "Couldn't load candidates")
      setToastFollowupRows([])
    } finally {
      setToastFollowupLoading(false)
    }
  }, [projectSlug, createdToast?.canonicalLabel])

  useEffect(() => {
    if (!createdToast || !projectSlug) {
      setToastFollowupRows([])
      setToastFollowupLoading(false)
      setToastFollowupError(null)
      setPotentialLinksOpen(false)
      setToastLinkBusyId(null)
      setToastLinkError(null)
      return
    }
    void prefetchToastFollowupCandidates()
  }, [createdToast, projectSlug, prefetchToastFollowupCandidates])

  function defaultNewCanonicalLabel(c: Candidate): string {
    const fromName = (c.suggested_name ?? "").trim()
    if (fromName) return fromName
    return (c.suggested_formatted_address ?? "").trim()
  }

  function openCreateCanonicalModal(c: Candidate) {
    setCreateModalId(c.id)
    setCreateCanonicalDraft(defaultNewCanonicalLabel(c))
    setCreateLinkNudge(null)
  }

  function closeCreateCanonicalModal() {
    setCreateModalId(null)
    setCreateCanonicalDraft("")
    setCreateLinkNudge(null)
  }

  async function submitCreateCanonicalFromModal() {
    if (!projectSlug || createModalId === null) return
    const name = createCanonicalDraft.trim()
    if (!name) {
      setError("Enter a label for the new canonical.")
      return
    }
    setAcceptingId(createModalId)
    setError(null)
    try {
      const acceptRes = await acceptCandidate(projectSlug, createModalId, { create_new: true, name })
      await refreshListQuiet()
      closeCreateCanonicalModal()
      const cid = acceptRes.stylebook_location_canonical_id
      if (typeof cid !== "number") {
        setError(
          "Canonical was created, but the server did not return its id. Reload the page if you need to link similar candidates from the toast.",
        )
        return
      }
      setCreatedToast({ canonicalLabel: name, canonicalId: cid })
    } catch (e) {
      setError(e instanceof Error ? e.message : "Accept failed")
    } finally {
      setAcceptingId(null)
    }
  }

  async function linkToastCandidateToNewCanonical(c: Candidate) {
    if (!projectSlug || !createdToast) return
    setToastLinkError(null)
    setToastLinkBusyId(c.id)
    try {
      await linkSubstrateToCanonical(c.id, projectSlug, createdToast.canonicalId)
      setToastFollowupRows((rows) => rows.filter((r) => r.id !== c.id))
      await refreshListQuiet()
    } catch (e) {
      setToastLinkError(e instanceof Error ? e.message : "Link failed")
    } finally {
      setToastLinkBusyId(null)
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

  function openNoteModal(c: Candidate) {
    setNoteModalId(c.id)
    const ctx = contextById[c.id]
    const initial = (c.note ?? ctx?.note ?? "") as string
    setNoteModalDraft(initial)
  }

  function closeNoteModal() {
    setNoteModalId(null)
    setNoteModalDraft("")
  }

  async function saveNoteFromModal() {
    if (!projectSlug || noteModalId === null) return
    const draft = noteModalDraft.trim()
    const id = noteModalId
    setNoteSavingId(id)
    setError(null)
    let ok = false
    try {
      await updateCandidateNote(projectSlug, id, draft ? draft : null)
      setContextById((prev) => {
        const existing = prev[id]
        if (!existing) return prev
        return { ...prev, [id]: { ...existing, note: draft ? draft : null } }
      })
      await refreshListQuiet()
      ok = true
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save note")
    } finally {
      setNoteSavingId(null)
    }
    if (ok) closeNoteModal()
  }

  return (
    <div className="container mx-auto p-6 space-y-6">
      {createdToast ? (
        <div className="fixed bottom-6 right-6 z-50 w-max max-w-[calc(100vw-3rem)]">
          <div
            role="status"
            className="rounded-xl border border-primary/25 bg-card text-card-foreground shadow-xl ring-2 ring-primary/15"
          >
            <div className="flex items-start gap-3 p-4 pr-2">
              <CheckCircle2
                className="mt-0.5 h-5 w-5 shrink-0 text-primary"
                aria-hidden
              />
              <div className="flex min-w-0 max-w-[min(28rem,calc(100vw-5.5rem))] flex-col gap-2">
                <div className="text-sm font-semibold leading-none">Canonical created</div>
                <div className="text-sm text-muted-foreground">
                  Saved as{" "}
                  <Link
                    to={`/locations/canonical/${createdToast.canonicalId}?project=${encodeURIComponent(projectSlug)}`}
                    className="font-medium text-foreground underline-offset-4 hover:underline break-words"
                  >
                    {createdToast.canonicalLabel}
                  </Link>
                </div>
                {toastFollowupLoading ? (
                  <div className="flex items-center gap-2 text-xs text-muted-foreground pt-0.5">
                    <Loader2 className="h-3.5 w-3.5 animate-spin shrink-0" aria-hidden />
                    <span>Checking the open queue for related locations…</span>
                  </div>
                ) : null}
                {toastFollowupError && !toastFollowupLoading ? (
                  <p className="text-xs text-destructive">{toastFollowupError}</p>
                ) : null}
                {!toastFollowupLoading && toastFollowupRows.length > 0 ? (
                  <Button
                    type="button"
                    size="sm"
                    className="mt-1 w-full shrink-0 self-start sm:w-auto"
                    onClick={() => setPotentialLinksOpen(true)}
                  >
                    Potential links found
                  </Button>
                ) : null}
              </div>
              <Button
                type="button"
                size="icon"
                variant="ghost"
                className="-mr-1 -mt-1 h-8 w-8 shrink-0"
                onClick={() => setCreatedToast(null)}
                aria-label="Dismiss"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </div>
      ) : null}
      <div className="flex justify-between items-center">
        <h1 className="text-3xl font-bold">Location candidates</h1>
        <Link to={`/locations/canonical?project=${projectSlug}`}>
          <Button variant="outline">Canonical locations</Button>
        </Link>
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
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Location</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Address</TableHead>
                  <TableHead>Created</TableHead>
                  <TableHead className="text-right">
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
                    return (
                    <Fragment key={c.id}>
                      <TableRow id={`candidate-row-${c.id}`}>
                        <TableCell className="font-medium">
                          <div className="flex flex-col items-start gap-1">
                          <div className="flex items-center gap-2">
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
                            <span>{c.suggested_name || "—"}</span>
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
                          {status === "deferred" && c.defer_display_message ? (
                            <p className="pl-10 text-xs text-muted-foreground max-w-md">
                              {c.defer_display_message}
                            </p>
                          ) : null}
                          </div>
                        </TableCell>
                        <TableCell>
                          {c.suggested_type
                            ? placeExtractTypeLabel(c.suggested_type)
                            : "—"}
                        </TableCell>
                        <TableCell className="max-w-xs truncate">
                          {c.suggested_formatted_address || "—"}
                        </TableCell>
                        <TableCell className="text-muted-foreground text-sm whitespace-nowrap">
                          {c.created_at ? new Date(c.created_at).toLocaleDateString() : "—"}
                        </TableCell>
                        <TableCell className="text-right w-[1%] whitespace-nowrap align-top">
                          <div className="inline-flex flex-nowrap items-center justify-end gap-1">
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
                                rowSug === "link"
                                  ? "Suggested: link to existing canonical"
                                  : "Link to existing canonical"
                              }
                              aria-label="Link to existing canonical"
                              disabled={acceptingId === c.id || deferringId === c.id}
                              onClick={() => {
                                setLinkModalId(c.id)
                                const preId =
                                  rowSug === "link" &&
                                  c.canonical_suggestion?.stylebook_location_canonical_id != null
                                    ? c.canonical_suggestion.stylebook_location_canonical_id
                                    : null
                                setLinkModalInitialCanonicalId(preId)
                              }}
                            >
                              <Link2 className="h-4 w-4" aria-hidden />
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
                            <Button
                              type="button"
                              size="icon"
                              variant="outline"
                              className="h-8 w-8 shrink-0"
                              title={c.note ? "Edit note" : "Add note"}
                              aria-label={c.note ? "Edit note" : "Add note"}
                              disabled={
                                acceptingId === c.id ||
                                deferringId === c.id ||
                                noteSavingId === c.id
                              }
                              onClick={() => openNoteModal(c)}
                            >
                              <StickyNote className="h-4 w-4" aria-hidden />
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                      {expandedId === c.id && (
                        <TableRow>
                          <TableCell colSpan={5} className="bg-muted/30">
                            <div className="space-y-3 py-2">
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
                              <div className="border-t border-border/60 pt-3 mt-3">
                                <div className="text-sm font-medium">Note</div>
                                {savedNoteText ? (
                                  <p className="mt-1 text-sm whitespace-pre-wrap">{savedNoteText}</p>
                                ) : (
                                  <p className="mt-1 text-sm text-muted-foreground italic">
                                    No note yet. Use the note (sticky note) action in the row to add one.
                                  </p>
                                )}
                              </div>
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
              {createModalCandidate?.suggested_type
                ? `Set the catalog label for this ${placeExtractTypeLabel(createModalCandidate.suggested_type)}. You can adjust spelling or add context (e.g. county) before saving.`
                : "Set the catalog label for this location before saving."}
            </DialogDescription>
          </DialogHeader>
          {createLinkNudge ? (
            <Alert className="border-amber-500/40 bg-amber-500/5">
              <AlertTitle className="text-amber-950 dark:text-amber-100">
                A similar canonical already exists
              </AlertTitle>
              <AlertDescription className="mt-2 space-y-3 text-amber-950/90 dark:text-amber-50/90">
                <p className="text-sm">
                  Before creating a new row, consider linking this candidate to{" "}
                  <span className="font-medium">{createLinkNudge.label}</span> instead.
                </p>
                <Button
                  type="button"
                  size="sm"
                  variant="secondary"
                  disabled={createModalId === null}
                  onClick={() => {
                    if (createModalId === null) return
                    setLinkModalId(createModalId)
                    setLinkModalInitialCanonicalId(createLinkNudge.canonicalId)
                    closeCreateCanonicalModal()
                  }}
                >
                  Open link flow
                </Button>
              </AlertDescription>
            </Alert>
          ) : null}
          <div className="space-y-2">
            <Label htmlFor="create-canonical-name">Canonical label</Label>
            <Input
              id="create-canonical-name"
              value={createCanonicalDraft}
              onChange={(e) => setCreateCanonicalDraft(e.target.value)}
              placeholder="e.g. Dolton, IL"
              autoFocus
            />
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
              disabled={acceptingId === createModalId || !createCanonicalDraft.trim()}
              onClick={() => void submitCreateCanonicalFromModal()}
            >
              {acceptingId === createModalId ? "Creating…" : "Create canonical"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={potentialLinksOpen}
        onOpenChange={(open) => {
          setPotentialLinksOpen(open)
          if (!open) {
            setToastLinkError(null)
            setToastLinkBusyId(null)
          }
        }}
      >
        <DialogContent className="max-w-2xl max-h-[min(90vh,720px)] flex flex-col">
          <DialogHeader>
            <DialogTitle>Potential links</DialogTitle>
            <DialogDescription>
              Open-queue locations that may match{" "}
              <span className="font-medium">{createdToast?.canonicalLabel ?? "—"}</span>. Link a
              row to attach it to this new canonical (
              <span className="font-medium">#{createdToast?.canonicalId ?? "—"}</span>). Ranked by
              text similarity (top 5).
            </DialogDescription>
          </DialogHeader>
          <div className="min-h-0 flex-1 space-y-3 overflow-y-auto">
            {toastFollowupLoading ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin shrink-0" aria-hidden />
                <span>Loading…</span>
              </div>
            ) : toastFollowupError ? (
              <p className="text-sm text-destructive">{toastFollowupError}</p>
            ) : toastFollowupRows.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No candidates in this list. Use Refresh if the queue has changed, or close when you are done.
              </p>
            ) : (
              <div className="overflow-hidden rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Location</TableHead>
                      <TableHead>Type</TableHead>
                      <TableHead>Address</TableHead>
                      <TableHead className="text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {toastFollowupRows.map((c) => (
                      <TableRow key={c.id}>
                        <TableCell className="font-medium">{c.suggested_name || "—"}</TableCell>
                        <TableCell className="text-muted-foreground text-sm">
                          {c.suggested_type ? placeExtractTypeLabel(c.suggested_type) : "—"}
                        </TableCell>
                        <TableCell className="text-muted-foreground text-sm max-w-[200px] truncate">
                          {c.suggested_formatted_address || "—"}
                        </TableCell>
                        <TableCell className="text-right">
                          <Button
                            type="button"
                            size="sm"
                            disabled={toastLinkBusyId !== null || !createdToast}
                            onClick={() => void linkToastCandidateToNewCanonical(c)}
                          >
                            {toastLinkBusyId === c.id ? (
                              <>
                                <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" aria-hidden />
                                Linking…
                              </>
                            ) : (
                              "Link"
                            )}
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
            {toastLinkError ? (
              <p className="text-sm text-destructive">{toastLinkError}</p>
            ) : null}
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => void prefetchToastFollowupCandidates()}
              disabled={toastFollowupLoading || !createdToast}
            >
              Refresh
            </Button>
            <Button type="button" onClick={() => setPotentialLinksOpen(false)}>
              Close
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={noteModalId !== null}
        onOpenChange={(open) => {
          if (!open && noteSavingId !== null) return
          if (!open) closeNoteModal()
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Review note</DialogTitle>
            <DialogDescription>
              {noteModalCandidate?.suggested_name
                ? `Optional note for “${noteModalCandidate.suggested_name}”.`
                : "Optional brief note for this candidate."}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="candidate-note-modal">Note</Label>
            <Textarea
              id="candidate-note-modal"
              rows={5}
              value={noteModalDraft}
              onChange={(e) => setNoteModalDraft(e.target.value)}
              placeholder="Add a brief note…"
            />
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              disabled={noteSavingId !== null}
              onClick={() => closeNoteModal()}
            >
              Cancel
            </Button>
            <Button
              type="button"
              disabled={noteSavingId !== null}
              onClick={() => void saveNoteFromModal()}
            >
              {noteSavingId !== null ? "Saving…" : "Save note"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
