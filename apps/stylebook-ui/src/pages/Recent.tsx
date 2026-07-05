import { useCallback, useEffect, useMemo, useState } from "react"
import { Breadcrumbs } from "@/components/Breadcrumbs"
import { StylebookHomeTabs } from "@/components/StylebookHomeTabs"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { listStylebookActivity, type StylebookActivityEvent } from "@/lib/api"
import { useScopeBreadcrumbRoot } from "@/lib/breadcrumbs"
import { useProjectCatalogScope } from "@/lib/catalogNavigation"

const PER_PAGE = 25

function eventSummary(event: StylebookActivityEvent): string {
  const base = event.event_type.replaceAll("_", " ")
  const entity = event.entity_label || event.entity_id || event.entity_type || "record"
  const related = event.related_entity_label || event.related_entity_id
  if (related) return `${base}: ${entity} -> ${related}`
  return `${base}: ${entity}`
}

export default function Recent() {
  const { stylebookSlug } = useProjectCatalogScope()
  const crumbRoot = useScopeBreadcrumbRoot()
  const [events, setEvents] = useState<StylebookActivityEvent[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [eventType, setEventType] = useState("")
  const [entityType, setEntityType] = useState("")
  const [source, setSource] = useState("")

  const totalPages = useMemo(() => Math.max(1, Math.ceil(total / PER_PAGE)), [total])

  const loadRecent = useCallback(async () => {
    if (!stylebookSlug) return
    setLoading(true)
    try {
      const response = await listStylebookActivity({
        stylebookSlug,
        page,
        perPage: PER_PAGE,
        eventType: eventType || undefined,
        entityType: entityType || undefined,
        source: source || undefined,
      })
      setEvents(response.events)
      setTotal(response.total)
    } finally {
      setLoading(false)
    }
  }, [stylebookSlug, page, eventType, entityType, source])

  useEffect(() => {
    void loadRecent()
  }, [loadRecent])

  useEffect(() => {
    setPage(1)
  }, [eventType, entityType, source])

  return (
    <div className="space-y-6">
      <div>
        <Breadcrumbs items={[{ label: crumbRoot.label }]} className="mb-3" />
        <h1 className="text-3xl font-bold">Recent</h1>
        <p className="text-muted-foreground mt-2">
          Track recent entity additions, links, merges, and review decisions.
        </p>
      </div>

      <StylebookHomeTabs />

      <div className="grid gap-3 md:grid-cols-3">
        <Input
          value={eventType}
          onChange={(event) => setEventType(event.target.value)}
          placeholder="Filter by event type"
        />
        <Input
          value={entityType}
          onChange={(event) => setEntityType(event.target.value)}
          placeholder="Filter by entity type"
        />
        <Input
          value={source}
          onChange={(event) => setSource(event.target.value)}
          placeholder="Filter by source"
        />
      </div>

      <div className="rounded-md border">
        {loading ? (
          <div className="p-6 text-sm text-muted-foreground">Loading recent activity...</div>
        ) : events.length === 0 ? (
          <div className="p-6 text-sm text-muted-foreground">No activity found for this view.</div>
        ) : (
          <ul className="divide-y">
            {events.map((event) => (
              <li key={event.id} className="p-4">
                <div className="text-sm font-medium">{eventSummary(event)}</div>
                <div className="mt-1 text-xs text-muted-foreground">
                  {new Date(event.created_at).toLocaleString()} - {event.source} - {event.actor_type}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          Page {page} of {totalPages}
        </p>
        <div className="flex gap-2">
          <Button
            variant="outline"
            disabled={page <= 1 || loading}
            onClick={() => setPage((value) => Math.max(1, value - 1))}
          >
            Previous
          </Button>
          <Button
            variant="outline"
            disabled={page >= totalPages || loading}
            onClick={() => setPage((value) => Math.min(totalPages, value + 1))}
          >
            Next
          </Button>
        </div>
      </div>
    </div>
  )
}
