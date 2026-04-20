import { Fragment, useCallback, useEffect, useMemo, useState } from "react"
import { Link, useSearchParams } from "react-router-dom"
import {
  acceptCandidate,
  deferCandidate,
  getCandidateContext,
  listCandidates,
  listLocationCandidateTypes,
  updateCandidateNote,
  type Candidate,
  type CandidateContextResponse,
} from "@/lib/api"
import { placeExtractTypeLabel } from "@/lib/place-extract-type-label"
import { CanonicalLinkModal } from "@/components/CanonicalLinkModal"
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
import { Textarea } from "@/components/ui/textarea"
import { cn } from "@/lib/utils"
import { ChevronRight, Link2, Loader2, PlusCircle, StickyNote } from "lucide-react"

/** Row action aligned with `canonical_suggestion.suggested_action` from the API. */
function suggestedRowAction(c: Candidate): "link" | "create_new" | null {
  const raw = c.canonical_suggestion?.suggested_action
  if (raw === "link_existing") return "link"
  if (raw === "materialize_new") return "create_new"
  return null
}

function suggestedActionShortLabel(c: Candidate): string | null {
  const sug = suggestedRowAction(c)
  if (sug === "link") return "Link to existing canonical"
  if (sug === "create_new") return "Create new canonical"
  return null
}

export default function LocationCandidates() {
  const [searchParams] = useSearchParams()
  const projectSlug = searchParams.get("project") || ""
  const [loading, setLoading] = useState(false)
  const [listTotal, setListTotal] = useState(0)
  const [candidates, setCandidates] = useState<Candidate[]>([])
  const [status, setStatus] = useState<"open" | "deferred">("open")
  const [query, setQuery] = useState("")
  const [debouncedQuery, setDebouncedQuery] = useState("")
  const [typeFilter, setTypeFilter] = useState<string>("all")
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
  const [error, setError] = useState<string | null>(null)

  const noteModalCandidate = useMemo(
    () => (noteModalId === null ? undefined : candidates.find((x) => x.id === noteModalId)),
    [candidates, noteModalId]
  )

  useEffect(() => {
    const t = window.setTimeout(() => setDebouncedQuery(query), 250)
    return () => window.clearTimeout(t)
  }, [query])

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

  const candidatesFilter = useMemo(() => {
    const tf = typeFilter === "all" ? undefined : typeFilter
    const q = debouncedQuery.trim() || undefined
    return { q, type_filter: tf }
  }, [debouncedQuery, typeFilter])

  const loadFlat = useCallback(async () => {
    const res = await listCandidates(projectSlug, status, false, {
      limit: 100,
      offset: 0,
      type_filter: candidatesFilter.type_filter,
      q: candidatesFilter.q,
    })
    setListTotal(res.total)
    setCandidates(res.candidates)
  }, [projectSlug, status, candidatesFilter])

  useEffect(() => {
    if (!projectSlug) return
    let cancelled = false
    void (async () => {
      setLoading(true)
      setError(null)
      try {
        await loadFlat()
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Request failed")
          setListTotal(0)
          setCandidates([])
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [projectSlug, status, loadFlat])

  async function handleAcceptNew(c: Candidate) {
    const name = (c.suggested_name || "").trim()
    if (!name || !projectSlug) return
    setAcceptingId(c.id)
    setError(null)
    try {
      await acceptCandidate(projectSlug, c.id, { create_new: true, name })
      await loadFlat()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Accept failed")
    } finally {
      setAcceptingId(null)
    }
  }

  async function handleDefer(c: Candidate) {
    if (!projectSlug) return
    setDeferringId(c.id)
    setError(null)
    try {
      await deferCandidate(projectSlug, c.id)
      await loadFlat()
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
      await loadFlat()
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
                  {types.map((t) => (
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
                      <TableRow>
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
                        <TableCell className="text-right">
                          <div className="flex flex-wrap justify-end gap-2">
                            <Button
                              size="sm"
                              variant={rowSug === "create_new" ? "outline" : "default"}
                              disabled={acceptingId === c.id || deferringId === c.id}
                              className={cn(
                                rowSug === "link" &&
                                  "ring-2 ring-primary ring-offset-2 ring-offset-background shadow-sm",
                              )}
                              title={rowSug === "link" ? "Suggested action for this location" : undefined}
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
                              <span className="inline-flex items-center gap-1.5">
                                <Link2 className="h-3.5 w-3.5" aria-hidden />
                                Link
                              </span>
                            </Button>
                            <Button
                              size="sm"
                              variant={rowSug === "create_new" ? "default" : "secondary"}
                              disabled={acceptingId === c.id || deferringId === c.id}
                              className={cn(
                                rowSug === "create_new" &&
                                  "ring-2 ring-primary ring-offset-2 ring-offset-background shadow-sm",
                              )}
                              title={
                                rowSug === "create_new"
                                  ? "Suggested action for this location"
                                  : undefined
                              }
                              onClick={() => void handleAcceptNew(c)}
                            >
                              <span className="inline-flex items-center gap-1.5">
                                <PlusCircle className="h-3.5 w-3.5" aria-hidden />
                                {acceptingId === c.id ? "Creating…" : "Create new"}
                              </span>
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
                              disabled={
                                acceptingId === c.id ||
                                deferringId === c.id ||
                                noteSavingId === c.id
                              }
                              onClick={() => openNoteModal(c)}
                            >
                              <span className="inline-flex items-center gap-1.5">
                                <StickyNote className="h-3.5 w-3.5" aria-hidden />
                                {c.note ? "Edit note" : "Note"}
                              </span>
                            </Button>
                            {status === "open" && (
                              <Button
                                size="sm"
                                variant="outline"
                                disabled={acceptingId === c.id || deferringId === c.id}
                                onClick={() => void handleDefer(c)}
                              >
                                {deferringId === c.id ? "Deferring…" : "Defer"}
                              </Button>
                            )}
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
                                    No note yet. Use the Note button in the row actions to add one.
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
        onDone={() => void loadFlat()}
      />

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
