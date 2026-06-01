import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react"
import { Link, useSearchParams } from "react-router-dom"
import { useProjectCatalogScope } from "@/lib/catalogNavigation"
import { useScopeBreadcrumbRoot } from "@/lib/breadcrumbs"
import { useSelectedStylebookLabel } from "@/lib/stylebookScopeContext"
import { fetchProjects, type Project } from "@/lib/api"
import {
  acceptPersonCandidate,
  deferPersonCandidate,
  getCanonicalPersonLegacy,
  getPersonCandidateContext,
  linkPersonSubstrateToCanonical,
  listPersonCandidates,
  listPersonCandidateTypes,
  type PersonCandidate,
  type PersonCandidateContextResponse,
} from "@/lib/api"
import { placeExtractTypeLabel, sortReviewQueueTypeFilterOptions } from "@/lib/place-extract-type-label"
import { PersonCanonicalLinkModal } from "@/components/PersonCanonicalLinkModal"
import { Button } from "@/components/ui/button"
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
import { Checkbox } from "@/components/ui/checkbox"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import Pagination from "@/components/Pagination"
import { cn } from "@/lib/utils"
import { Breadcrumbs } from "@/components/Breadcrumbs"
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

const REVIEW_QUEUE_PAGE_SIZE = 100

function suggestedRowAction(c: PersonCandidate): "link" | "create_new" | "defer" | null {
  const raw = c.canonical_suggestion?.suggested_action
  if (raw === "link_existing") return "link"
  if (raw === "materialize_new") return "create_new"
  if (raw === "defer") return "defer"
  return null
}

function suggestedActionShortLabel(c: PersonCandidate): string | null {
  const sug = suggestedRowAction(c)
  if (sug === "link") return "Link to existing person"
  if (sug === "create_new") return "Create new person"
  if (sug === "defer") return "Defer (remove from linking queue)"
  return null
}

export default function PersonCandidates() {
  const {
    projectScopeSlug,
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
  const [listFetchGen, setListFetchGen] = useState(0)
  const filterKeySeenRef = useRef<string | null>(null)
  const [candidates, setCandidates] = useState<PersonCandidate[]>([])
  const [status, setStatus] = useState<"open" | "deferred">("open")
  const [query, setQuery] = useState("")
  const [debouncedQuery, setDebouncedQuery] = useState("")
  const [typeFilter, setTypeFilter] = useState<string>("all")
  const [needsReviewOnly, setNeedsReviewOnly] = useState(false)
  const filterKey = useMemo(
    () =>
      `${projectSlug}|${stylebookSlug}|${status}|${debouncedQuery}|${typeFilter}|${needsReviewOnly}`,
    [projectSlug, stylebookSlug, status, debouncedQuery, typeFilter, needsReviewOnly],
  )
  const [types, setTypes] = useState<string[]>([])
  const [acceptingId, setAcceptingId] = useState<number | null>(null)
  const [deferringId, setDeferringId] = useState<number | null>(null)
  const [linkModalId, setLinkModalId] = useState<number | null>(null)
  const [linkModalInitialCanonicalId, setLinkModalInitialCanonicalId] = useState<string | null>(null)
  const [linkModalSearchQuery, setLinkModalSearchQuery] = useState<string | null>(null)
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [contextById, setContextById] = useState<Record<number, PersonCandidateContextResponse>>({})
  const [contextLoadingId, setContextLoadingId] = useState<number | null>(null)
  const [createModalId, setCreateModalId] = useState<number | null>(null)
  const [createLabelDraft, setCreateLabelDraft] = useState("")
  const [createTitleDraft, setCreateTitleDraft] = useState("")
  const [createAffiliationDraft, setCreateAffiliationDraft] = useState("")
  const [createPublicFigure, setCreatePublicFigure] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [linkedToast, setLinkedToast] = useState<{
    canonicalId: string
    canonicalLabel: string
    candidateLabel: string
  } | null>(null)
  const [linkingSuggestedId, setLinkingSuggestedId] = useState<number | null>(null)

  const orderedTypeFilterOptions = useMemo(
    () => sortReviewQueueTypeFilterOptions(types),
    [types],
  )

  const listTotalPages = useMemo(
    () => Math.max(1, Math.ceil(listTotal / REVIEW_QUEUE_PAGE_SIZE)),
    [listTotal],
  )

  useEffect(() => {
    let cancelled = false
    setProjectsLoading(true)
    void fetchProjects()
      .then((rows) => {
        if (!cancelled) setProjects(rows)
      })
      .catch(() => {
        if (!cancelled) setProjects([])
      })
      .finally(() => {
        if (!cancelled) setProjectsLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

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

  useEffect(() => {
    if (!projectSlug) return
    void (async () => {
      try {
        const res = await listPersonCandidateTypes(projectSlug, status)
        setTypes(res.types)
      } catch {
        setTypes([])
      }
    })()
  }, [projectSlug, status])

  const refreshListQuiet = useCallback(async () => {
    if (!projectSlug) return
    setError(null)
    const type_filter = typeFilter === "all" ? undefined : typeFilter
    const q = debouncedQuery.trim() || undefined
    const offset = (listPage - 1) * REVIEW_QUEUE_PAGE_SIZE
    try {
      const res = await listPersonCandidates(projectSlug, status, {
        limit: REVIEW_QUEUE_PAGE_SIZE,
        offset,
        type_filter,
        q,
        needs_review: status === "open" && needsReviewOnly ? true : undefined,
      })
      setListTotal(res.total)
      setCandidates(res.candidates)
      setListHasNext(res.has_next)
      setListHasPrev(res.has_prev)
      if (res.candidates.length === 0 && res.total > 0 && offset >= REVIEW_QUEUE_PAGE_SIZE) {
        setListPage((p) => Math.max(1, p - 1))
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request failed")
    }
  }, [projectSlug, status, debouncedQuery, typeFilter, listPage, needsReviewOnly])

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
        const res = await listPersonCandidates(projectSlug, status, {
          limit: REVIEW_QUEUE_PAGE_SIZE,
          offset,
          type_filter,
          q,
          needs_review: status === "open" && needsReviewOnly ? true : undefined,
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
  }, [projectSlug, status, debouncedQuery, typeFilter, listPage, listFetchGen, needsReviewOnly])

  function openCreateModal(c: PersonCandidate) {
    setCreateModalId(c.id)
    setCreateLabelDraft((c.suggested_name ?? "").trim())
    setCreateTitleDraft((c.suggested_title ?? "").trim())
    setCreateAffiliationDraft((c.suggested_affiliation ?? "").trim())
    setCreatePublicFigure(Boolean(c.suggested_public_figure))
  }

  function closeCreateModal() {
    setCreateModalId(null)
    setCreateLabelDraft("")
    setCreateTitleDraft("")
    setCreateAffiliationDraft("")
    setCreatePublicFigure(false)
  }

  async function submitCreateFromModal() {
    if (!projectSlug || createModalId === null) return
    const label = createLabelDraft.trim()
    if (!label) {
      setError("Enter a name for the new person.")
      return
    }
    setAcceptingId(createModalId)
    setError(null)
    try {
      await acceptPersonCandidate(projectSlug, createModalId, {
        create_new: true,
        label,
        title: createTitleDraft.trim() || null,
        affiliation: createAffiliationDraft.trim() || null,
        public_figure: createPublicFigure,
        person_type: createModalCandidate?.suggested_type ?? null,
      })
      await refreshListQuiet()
      closeCreateModal()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Accept failed")
    } finally {
      setAcceptingId(null)
    }
  }

  const createModalCandidate = useMemo(
    () => (createModalId === null ? undefined : candidates.find((x) => x.id === createModalId)),
    [candidates, createModalId],
  )

  async function linkCandidateToSuggestedCanonical(c: PersonCandidate) {
    if (!projectSlug) return
    const cid = (c.canonical_suggestion?.stylebook_person_canonical_id ?? "").trim()
    if (!cid) return
    setLinkingSuggestedId(c.id)
    setError(null)
    try {
      await linkPersonSubstrateToCanonical(c.id, projectSlug, cid)
      let canonLabel = cid
      try {
        const canon = await getCanonicalPersonLegacy(cid, projectSlug)
        canonLabel = (canon.label ?? "").trim() || cid
      } catch {
        // ignore
      }
      setLinkedToast({
        canonicalId: cid,
        canonicalLabel: canonLabel,
        candidateLabel: (c.suggested_name ?? "").trim() || `Person ${c.id}`,
      })
      await refreshListQuiet()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Link failed")
    } finally {
      setLinkingSuggestedId(null)
    }
  }

  async function handleDefer(c: PersonCandidate) {
    if (!projectSlug) return
    setDeferringId(c.id)
    setError(null)
    try {
      await deferPersonCandidate(projectSlug, c.id)
      await refreshListQuiet()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Defer failed")
    } finally {
      setDeferringId(null)
    }
  }

  async function toggleExpanded(c: PersonCandidate) {
    if (!projectSlug) return
    const next = expandedId === c.id ? null : c.id
    setExpandedId(next)
    if (next === null) return
    if (contextById[next]) return
    setContextLoadingId(next)
    try {
      const ctx = await getPersonCandidateContext(projectSlug, next, 3)
      setContextById((prev) => ({ ...prev, [next]: ctx }))
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load context")
    } finally {
      setContextLoadingId(null)
    }
  }

  return (
    <div className="container mx-auto p-6 space-y-6">
      {linkedToast ? (
        <div className="fixed bottom-6 right-6 z-50 w-max max-w-[calc(100vw-3rem)]">
          <div className="rounded-xl border border-primary/25 bg-card text-card-foreground shadow-xl ring-2 ring-primary/15 p-4 flex items-start gap-3">
            <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-primary" aria-hidden />
            <div className="text-sm">
              <div className="font-semibold">Linked to person</div>
              <div className="text-muted-foreground mt-1">
                {linkedToast.candidateLabel} →{" "}
                <Link
                  to={`${catalogBasePath}/people/canonical/${linkedToast.canonicalId}${filterScopeSuffix}`}
                  className="font-medium text-foreground underline-offset-4 hover:underline"
                >
                  {linkedToast.canonicalLabel}
                </Link>
              </div>
            </div>
            <Button
              type="button"
              size="icon"
              variant="ghost"
              className="h-8 w-8 shrink-0"
              onClick={() => setLinkedToast(null)}
              aria-label="Dismiss"
            >
              <X className="h-4 w-4" />
            </Button>
          </div>
        </div>
      ) : null}

      <div className="flex justify-between items-center">
        <div className="min-w-0">
          <Breadcrumbs
            className="mb-3"
            items={[
              { label: crumbRoot.label, to: crumbRoot.to },
              { label: "People", to: `${catalogBasePath}/people/canonical${filterScopeSuffix}` },
              { label: "Candidates" },
            ]}
          />
          <h1 className="text-3xl font-bold">People candidates</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Link candidates from{" "}
            <span className="font-semibold text-foreground">{projectDisplayName}</span> to Stylebook{" "}
            <span className="font-semibold text-foreground">{stylebookLabel}</span>
          </p>
        </div>
        <div className="flex items-center gap-2">
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
          <Link to={`${catalogBasePath}/people/canonical${filterScopeSuffix}`}>
            <Button variant="outline">Canonical people</Button>
          </Link>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Review queue</CardTitle>
          <CardDescription>
            Unlinked people for this project. Use Link to attach to an existing person, or Create
            new to add one.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="person-candidate-search">Search</Label>
            <Input
              id="person-candidate-search"
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
            {status === "open" ? (
              <div className="flex items-center gap-2 pb-2">
                <Checkbox
                  id="person-needs-review-only"
                  checked={needsReviewOnly}
                  onCheckedChange={(v) => setNeedsReviewOnly(v === true)}
                />
                <Label htmlFor="person-needs-review-only" className="font-normal cursor-pointer">
                  Flagged for identity review only
                </Label>
              </div>
            ) : null}
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
              {(["open", "deferred"] as const).map((tab) => (
                <button
                  key={tab}
                  type="button"
                  role="tab"
                  aria-selected={status === tab}
                  disabled={loading}
                  className={cn(
                    "whitespace-nowrap border-b-2 -mb-px py-3 text-sm font-medium transition-colors",
                    status === tab
                      ? "border-primary text-foreground"
                      : "border-transparent text-muted-foreground hover:text-foreground",
                  )}
                  onClick={() => setStatus(tab)}
                >
                  {tab === "open" ? "For review" : "Deferred"}
                </button>
              ))}
            </div>
            <Table className="table-fixed">
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Title</TableHead>
                  <TableHead>Affiliation</TableHead>
                  <TableHead className="text-right">
                    <span className="sr-only">Actions</span>
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {candidates.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={5} className="text-muted-foreground">
                      No unlinked people.
                    </TableCell>
                  </TableRow>
                ) : (
                  candidates.map((c) => {
                    const rowSug = suggestedRowAction(c)
                    const rowSugLabel = suggestedActionShortLabel(c)
                    const suggestedCanonicalId =
                      rowSug === "link" &&
                      c.canonical_suggestion?.stylebook_person_canonical_id != null
                        ? String(c.canonical_suggestion.stylebook_person_canonical_id).trim()
                        : ""
                    const typeLabel = c.suggested_type
                      ? placeExtractTypeLabel(c.suggested_type)
                      : "—"
                    return (
                      <Fragment key={c.id}>
                        <TableRow>
                          <TableCell className="font-medium min-w-0">
                            <div className="flex flex-col gap-1">
                              <div className="flex items-center gap-2 min-w-0">
                                <Button
                                  type="button"
                                  size="icon"
                                  variant="ghost"
                                  className="h-8 w-8 shrink-0"
                                  onClick={() => void toggleExpanded(c)}
                                  disabled={contextLoadingId === c.id}
                                  aria-expanded={expandedId === c.id}
                                >
                                  {contextLoadingId === c.id ? (
                                    <Loader2 className="h-4 w-4 animate-spin" />
                                  ) : (
                                    <ChevronRight
                                      className={cn(
                                        "h-4 w-4 transition-transform",
                                        expandedId === c.id && "rotate-90",
                                      )}
                                    />
                                  )}
                                </Button>
                                <span className="min-w-0 break-words">{c.suggested_name || "—"}</span>
                                {c.note ? (
                                  <StickyNote className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
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
                                <p className="pl-10 text-xs text-muted-foreground">{c.defer_display_message}</p>
                              ) : null}
                            </div>
                          </TableCell>
                          <TableCell>{typeLabel}</TableCell>
                          <TableCell className="truncate">{c.suggested_title || "—"}</TableCell>
                          <TableCell className="truncate">{c.suggested_affiliation || "—"}</TableCell>
                          <TableCell className="text-right whitespace-nowrap">
                            <div className="inline-flex items-center gap-1.5">
                              <Button
                                type="button"
                                size="icon"
                                variant={rowSug === "link" ? "default" : "outline"}
                                className="h-8 w-8"
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
                                  setLinkModalSearchQuery((c.suggested_name ?? "").trim() || null)
                                }}
                              >
                                {linkingSuggestedId === c.id ? (
                                  <Loader2 className="h-4 w-4 animate-spin" />
                                ) : (
                                  <Link2 className="h-4 w-4" />
                                )}
                              </Button>
                              <Button
                                type="button"
                                size="icon"
                                variant={rowSug === "create_new" ? "default" : "secondary"}
                                className="h-8 w-8"
                                disabled={acceptingId === c.id || deferringId === c.id}
                                onClick={() => openCreateModal(c)}
                              >
                                {acceptingId === c.id ? (
                                  <Loader2 className="h-4 w-4 animate-spin" />
                                ) : (
                                  <PlusCircle className="h-4 w-4" />
                                )}
                              </Button>
                              {status === "open" && (
                                <Button
                                  type="button"
                                  size="icon"
                                  variant={rowSug === "defer" ? "default" : "outline"}
                                  className="h-8 w-8"
                                  disabled={acceptingId === c.id || deferringId === c.id}
                                  onClick={() => void handleDefer(c)}
                                >
                                  {deferringId === c.id ? (
                                    <Loader2 className="h-4 w-4 animate-spin" />
                                  ) : (
                                    <Clock className="h-4 w-4" />
                                  )}
                                </Button>
                              )}
                            </div>
                          </TableCell>
                        </TableRow>
                        {expandedId === c.id && (
                          <TableRow>
                            <TableCell colSpan={5} className="bg-muted/30">
                              <div className="py-2 space-y-2">
                                <div className="text-sm font-medium">Context</div>
                                {contextLoadingId === c.id ? (
                                  <div className="flex items-center gap-2 text-sm text-muted-foreground">
                                    <Loader2 className="h-4 w-4 animate-spin" />
                                    Loading…
                                  </div>
                                ) : (contextById[c.id]?.examples?.length ?? 0) === 0 ? (
                                  <div className="text-sm text-muted-foreground">No article examples found.</div>
                                ) : (
                                  <ul className="space-y-1 text-sm">
                                    {contextById[c.id].examples.map((ex) => (
                                      <li key={ex.article_id}>
                                        <span className="text-muted-foreground">
                                          {ex.article_headline ?? `Article ${ex.article_id}`}:
                                        </span>{" "}
                                        {ex.text}
                                      </li>
                                    ))}
                                  </ul>
                                )}
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

      <PersonCanonicalLinkModal
        open={linkModalId !== null}
        onOpenChange={(o) => {
          if (!o) {
            setLinkModalId(null)
            setLinkModalInitialCanonicalId(null)
            setLinkModalSearchQuery(null)
          }
        }}
        projectSlug={projectSlug}
        substratePersonId={linkModalId}
        initialCanonicalId={linkModalInitialCanonicalId}
        initialSearchQuery={linkModalSearchQuery}
        title="Link candidate to person"
        onLinked={({ id, label }) => {
          setLinkedToast({
            canonicalId: id,
            canonicalLabel: label,
            candidateLabel:
              (candidates.find((c) => c.id === linkModalId)?.suggested_name ?? "").trim() ||
              (linkModalId != null ? `Person ${linkModalId}` : "Person"),
          })
        }}
        onDone={() => void refreshListQuiet()}
      />

      <Dialog
        open={createModalId !== null}
        onOpenChange={(open) => {
          if (!open && acceptingId === createModalId) return
          if (!open) closeCreateModal()
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Create new person</DialogTitle>
            <DialogDescription>
              Add a canonical person to{" "}
              <span className="font-semibold text-foreground">{stylebookLabel}</span>
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="create-person-name">Name</Label>
              <Input
                id="create-person-name"
                value={createLabelDraft}
                onChange={(e) => setCreateLabelDraft(e.target.value)}
                autoFocus
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="create-person-title">Title</Label>
              <Input
                id="create-person-title"
                value={createTitleDraft}
                onChange={(e) => setCreateTitleDraft(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="create-person-affiliation">Affiliation</Label>
              <Input
                id="create-person-affiliation"
                value={createAffiliationDraft}
                onChange={(e) => setCreateAffiliationDraft(e.target.value)}
              />
            </div>
            <div className="flex items-center gap-2">
              <Checkbox
                id="create-person-public"
                checked={createPublicFigure}
                onCheckedChange={(v) => setCreatePublicFigure(v === true)}
              />
              <Label htmlFor="create-person-public">Public figure</Label>
            </div>
            {createModalCandidate?.suggested_type ? (
              <p className="text-xs text-muted-foreground">
                Type: {placeExtractTypeLabel(createModalCandidate.suggested_type)}
              </p>
            ) : null}
          </div>
          <DialogFooter>
            <Button variant="outline" disabled={acceptingId === createModalId} onClick={closeCreateModal}>
              Cancel
            </Button>
            <Button
              disabled={acceptingId === createModalId || !createLabelDraft.trim()}
              onClick={() => void submitCreateFromModal()}
            >
              {acceptingId === createModalId ? "Creating…" : "Create person"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
