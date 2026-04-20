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
import { CanonicalLinkModal } from "@/components/CanonicalLinkModal"
import { Button } from "@/components/ui/button"
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
import { Loader2 } from "lucide-react"

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
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [contextById, setContextById] = useState<Record<number, CandidateContextResponse>>({})
  const [contextLoadingId, setContextLoadingId] = useState<number | null>(null)
  const [noteDraftById, setNoteDraftById] = useState<Record<number, string>>({})
  const [noteSavingId, setNoteSavingId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const t = window.setTimeout(() => setDebouncedQuery(query), 250)
    return () => window.clearTimeout(t)
  }, [query])

  useEffect(() => {
    if (!projectSlug) return
    void (async () => {
      try {
        const res = await listLocationCandidateTypes(projectSlug, "open")
        setTypes(res.types)
      } catch {
        setTypes([])
      }
    })()
  }, [projectSlug])

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
      if (ctx.note !== undefined && ctx.note !== null) {
        setNoteDraftById((prev) => ({ ...prev, [next]: ctx.note ?? "" }))
      } else if (c.note) {
        setNoteDraftById((prev) => ({ ...prev, [next]: c.note ?? "" }))
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load context")
    } finally {
      setContextLoadingId(null)
    }
  }

  async function saveNote(c: Candidate) {
    if (!projectSlug) return
    const draft = (noteDraftById[c.id] ?? "").trim()
    setNoteSavingId(c.id)
    try {
      await updateCandidateNote(projectSlug, c.id, draft ? draft : null)
      setContextById((prev) => {
        const existing = prev[c.id]
        if (!existing) return prev
        return { ...prev, [c.id]: { ...existing, note: draft ? draft : null } }
      })
      await loadFlat()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save note")
    } finally {
      setNoteSavingId(null)
    }
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
            Unlinked locations for this project. Use “Link to canonical” to link the item to an
            existing canonical, or “Accept as new” to create a new one.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-2 items-center">
            <Button
              variant={status === "open" ? "default" : "outline"}
              size="sm"
              onClick={() => setStatus("open")}
              disabled={loading}
            >
              For review
            </Button>
            <Button
              variant={status === "deferred" ? "default" : "outline"}
              size="sm"
              onClick={() => setStatus("deferred")}
              disabled={loading}
            >
              Deferred
            </Button>
            <div className="ml-auto flex flex-wrap gap-2 items-end">
              <div className="w-[220px]">
                <Label>Search</Label>
                <Input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search name…"
                />
              </div>
              <div className="w-[220px]">
                <Label>Type</Label>
                <Select value={typeFilter} onValueChange={setTypeFilter}>
                  <SelectTrigger>
                    <SelectValue placeholder="All types" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All</SelectItem>
                    {types.map((t) => (
                      <SelectItem key={t} value={t}>
                        {t}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            {loading && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Created</TableHead>
                  <TableHead>Address</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
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
                  candidates.map((c) => (
                    <Fragment key={c.id}>
                      <TableRow>
                        <TableCell className="font-medium">
                          <div className="flex items-center gap-2">
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => void toggleExpanded(c)}
                              disabled={contextLoadingId === c.id}
                            >
                              {expandedId === c.id ? "Hide" : "Show"}
                            </Button>
                            <span>{c.suggested_name || "—"}</span>
                            {c.note ? (
                              <span className="text-xs text-muted-foreground">(note)</span>
                            ) : null}
                          </div>
                        </TableCell>
                        <TableCell>{c.suggested_type || "—"}</TableCell>
                        <TableCell className="text-muted-foreground text-sm whitespace-nowrap">
                          {c.created_at ? new Date(c.created_at).toLocaleDateString() : "—"}
                        </TableCell>
                        <TableCell className="max-w-xs truncate">
                          {c.suggested_formatted_address || "—"}
                        </TableCell>
                        <TableCell className="text-right space-x-2">
                          <Button
                            size="sm"
                            variant="default"
                            disabled={acceptingId === c.id || deferringId === c.id}
                            onClick={() => setLinkModalId(c.id)}
                          >
                            Link to canonical
                          </Button>
                          <Button
                            size="sm"
                            variant="secondary"
                            disabled={acceptingId === c.id || deferringId === c.id}
                            onClick={() => void handleAcceptNew(c)}
                          >
                            {acceptingId === c.id ? "Accepting…" : "Accept as new"}
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
                              <div>
                                <div className="text-sm font-medium">Note</div>
                                <Textarea
                                  value={noteDraftById[c.id] ?? c.note ?? ""}
                                  onChange={(e) =>
                                    setNoteDraftById((prev) => ({
                                      ...prev,
                                      [c.id]: e.target.value,
                                    }))
                                  }
                                  placeholder="Add a brief note…"
                                />
                                <div className="mt-2 flex justify-end">
                                  <Button
                                    size="sm"
                                    variant="secondary"
                                    disabled={noteSavingId === c.id}
                                    onClick={() => void saveNote(c)}
                                  >
                                    {noteSavingId === c.id ? "Saving…" : "Save note"}
                                  </Button>
                                </div>
                              </div>
                            </div>
                          </TableCell>
                        </TableRow>
                      )}
                    </Fragment>
                  ))
                )}
              </TableBody>
            </Table>
          </>
        </CardContent>
      </Card>

      <CanonicalLinkModal
        open={linkModalId !== null}
        onOpenChange={(o) => {
          if (!o) setLinkModalId(null)
        }}
        projectSlug={projectSlug}
        substrateLocationId={linkModalId}
        title="Link candidate to canonical"
        onDone={() => void loadFlat()}
      />
    </div>
  )
}
