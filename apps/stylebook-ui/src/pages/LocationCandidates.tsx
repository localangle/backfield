import { useEffect, useState } from "react"
import { Link, useSearchParams } from "react-router-dom"
import { listClusters, listCandidates } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Loader2 } from "lucide-react"

export default function LocationCandidates() {
  const [searchParams] = useSearchParams()
  const projectSlug = searchParams.get("project") || ""
  const [loading, setLoading] = useState(false)
  const [clusterMode, setClusterMode] = useState(true)
  const [clusterTotal, setClusterTotal] = useState(0)
  const [listTotal, setListTotal] = useState(0)

  useEffect(() => {
    if (!projectSlug) return
    let cancelled = false
    void (async () => {
      setLoading(true)
      try {
        if (clusterMode) {
          const res = await listClusters(projectSlug, "open", { limit: 25, offset: 0 })
          if (!cancelled) setClusterTotal(res.total)
        } else {
          const res = await listCandidates(projectSlug, "open", false, { limit: 25, offset: 0 })
          if (!cancelled) setListTotal(res.total)
        }
      } catch {
        if (!cancelled) {
          setClusterTotal(0)
          setListTotal(0)
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [projectSlug, clusterMode])

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
            Backfield exposes empty candidate responses until a review pipeline is connected to
            substrate data. You can still manage canonical locations for this project.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex gap-2 items-center">
            <Button variant={clusterMode ? "default" : "outline"} size="sm" onClick={() => setClusterMode(true)}>
              Clustered view
            </Button>
            <Button variant={!clusterMode ? "default" : "outline"} size="sm" onClick={() => setClusterMode(false)}>
              Flat list
            </Button>
            {loading && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
          </div>
          <p className="text-sm text-muted-foreground">
            {clusterMode
              ? `Clusters from API: ${clusterTotal} (stub)`
              : `Ungrouped candidates from API: ${listTotal} (stub)`}
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
