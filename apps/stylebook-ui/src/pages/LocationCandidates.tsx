import { useCallback, useEffect, useState } from "react"
import { Link, useSearchParams } from "react-router-dom"
import { acceptCandidate, listCandidates, listClusters, type Candidate } from "@/lib/api"
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
  const [clusterMode, setClusterMode] = useState(false)
  const [clusterTotal, setClusterTotal] = useState(0)
  const [listTotal, setListTotal] = useState(0)
  const [candidates, setCandidates] = useState<Candidate[]>([])
  const [needsReviewOnly, setNeedsReviewOnly] = useState(false)
  const [acceptingId, setAcceptingId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  const loadClusters = useCallback(async () => {
    const res = await listClusters(projectSlug, "open", { limit: 25, offset: 0 })
    setClusterTotal(res.total)
  }, [projectSlug])

  const loadFlat = useCallback(async () => {
    const res = await listCandidates(projectSlug, "open", false, {
      limit: 100,
      offset: 0,
      needs_review: needsReviewOnly ? true : undefined,
    })
    setListTotal(res.total)
    setCandidates(res.candidates)
  }, [projectSlug, needsReviewOnly])

  useEffect(() => {
    if (!projectSlug) return
    let cancelled = false
    void (async () => {
      setLoading(true)
      setError(null)
      try {
        if (clusterMode) {
          await loadClusters()
        } else {
          await loadFlat()
        }
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Request failed")
          setClusterTotal(0)
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
  }, [projectSlug, clusterMode, loadClusters, loadFlat])

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
            Open substrate locations for this project (not yet linked to a Stylebook canonical). Use
            “Accept as new” to create a canonical and link this row.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-2 items-center">
            <Button variant={!clusterMode ? "default" : "outline"} size="sm" onClick={() => setClusterMode(false)}>
              Open queue (table)
            </Button>
            <Button variant={clusterMode ? "default" : "outline"} size="sm" onClick={() => setClusterMode(true)}>
              Clusters (preview)
            </Button>
            {!clusterMode && (
              <label className="flex items-center gap-2 text-sm text-muted-foreground ml-2">
                <input
                  type="checkbox"
                  checked={needsReviewOnly}
                  onChange={(ev) => setNeedsReviewOnly(ev.target.checked)}
                />
                Needs review only
              </label>
            )}
            {loading && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
          {clusterMode ? (
            <p className="text-sm text-muted-foreground">Clusters from API: {clusterTotal}</p>
          ) : (
            <>
              <p className="text-sm text-muted-foreground">Open candidates: {listTotal}</p>
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
                        No rows in the open queue.
                      </TableCell>
                    </TableRow>
                  ) : (
                    candidates.map((c) => (
                      <TableRow key={c.id}>
                        <TableCell className="font-medium">{c.suggested_name || "—"}</TableCell>
                        <TableCell>{c.suggested_type || "—"}</TableCell>
                        <TableCell className="max-w-xs truncate">{c.suggested_formatted_address || "—"}</TableCell>
                        <TableCell className="text-right">
                          <Button
                            size="sm"
                            variant="secondary"
                            disabled={acceptingId === c.id}
                            onClick={() => void handleAcceptNew(c)}
                          >
                            {acceptingId === c.id ? "Linking…" : "Accept as new"}
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
