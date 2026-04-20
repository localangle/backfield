import { useCallback, useEffect, useState } from "react"
import { Link, useSearchParams } from "react-router-dom"
import { acceptCandidate, deferCandidate, listCandidates, type Candidate } from "@/lib/api"
import { CanonicalLinkModal } from "@/components/CanonicalLinkModal"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Loader2 } from "lucide-react"

export default function LocationCandidates() {
  const [searchParams] = useSearchParams()
  const projectSlug = searchParams.get("project") || ""
  const [loading, setLoading] = useState(false)
  const [listTotal, setListTotal] = useState(0)
  const [candidates, setCandidates] = useState<Candidate[]>([])
  const [status, setStatus] = useState<"open" | "deferred">("open")
  const [acceptingId, setAcceptingId] = useState<number | null>(null)
  const [deferringId, setDeferringId] = useState<number | null>(null)
  const [linkModalId, setLinkModalId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  const loadFlat = useCallback(async () => {
    const res = await listCandidates(projectSlug, status, false, {
      limit: 100,
      offset: 0,
    })
    setListTotal(res.total)
    setCandidates(res.candidates)
  }, [projectSlug, status])

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
            {loading && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Address</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {candidates.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={4} className="text-muted-foreground">
                      No unlinked locations.
                    </TableCell>
                  </TableRow>
                ) : (
                  candidates.map((c) => (
                    <TableRow key={c.id}>
                      <TableCell className="font-medium">{c.suggested_name || "—"}</TableCell>
                      <TableCell>{c.suggested_type || "—"}</TableCell>
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
