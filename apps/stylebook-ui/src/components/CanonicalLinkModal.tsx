import { useEffect, useMemo, useState } from "react"
import {
  getCanonicalLocationLegacy,
  getLocation,
  getSuggestedCanonicals,
  linkSubstrateToCanonical,
  listCanonicalLocationsLegacy,
  type CanonicalLocation,
  type SuggestedCanonicalItem,
} from "@/lib/api"
import { LinkPickTable, type LinkPickTableRow } from "@/components/LinkPickTable"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { placeExtractTypeLabel } from "@/lib/place-extract-type-label"
import { useSelectedStylebookLabel } from "@/lib/stylebookScopeContext"
import { Loader2 } from "lucide-react"

function canonicalToSuggestedRow(c: CanonicalLocation): SuggestedCanonicalItem {
  return {
    canonical_id: c.id,
    label: c.label,
    location_type: c.location_type ?? null,
    formatted_address: c.formatted_address ?? null,
  }
}

function suggestedItemsToPickRows(items: SuggestedCanonicalItem[]): LinkPickTableRow[] {
  return items.map((s) => ({
    rowKey: s.canonical_id,
    location: s.label,
    typeLabel:
      s.location_type && String(s.location_type).trim()
        ? placeExtractTypeLabel(s.location_type)
        : "—",
    address: (s.formatted_address ?? "").trim() || "—",
  }))
}

export function CanonicalLinkModal(props: {
  open: boolean
  onOpenChange: (open: boolean) => void
  projectSlug: string
  /** Substrate location id (open candidate or linked row for relink/move). */
  substrateLocationId: number | null
  onDone: () => void
  onLinked?: (canonical: { id: string; label: string }) => void
  title?: string
  /** When set, surface this canonical first (e.g. pre-filled from row suggestion). */
  initialCanonicalId?: string | null
}) {
  const { open, onOpenChange, projectSlug, substrateLocationId, onDone, title, initialCanonicalId } =
    props
  const stylebookLabel = useSelectedStylebookLabel()
  const [suggestions, setSuggestions] = useState<SuggestedCanonicalItem[]>([])
  const [loadingSuggestions, setLoadingSuggestions] = useState(false)
  const [searchQ, setSearchQ] = useState("")
  const [searchLoading, setSearchLoading] = useState(false)
  const [searchHits, setSearchHits] = useState<CanonicalLocation[]>([])
  const [linkingCanonicalId, setLinkingCanonicalId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [initialCanonExtra, setInitialCanonExtra] = useState<CanonicalLocation | null>(null)
  const [linkedCanonicalId, setLinkedCanonicalId] = useState<string | null>(null)
  const [linkedMetaLoaded, setLinkedMetaLoaded] = useState(false)

  useEffect(() => {
    if (!open) {
      setSearchQ("")
      setSearchHits([])
      setError(null)
      setLinkingCanonicalId(null)
      setInitialCanonExtra(null)
      setLinkedCanonicalId(null)
      setLinkedMetaLoaded(false)
    }
  }, [open])

  useEffect(() => {
    if (!open || substrateLocationId == null || !projectSlug) {
      setLinkedCanonicalId(null)
      setLinkedMetaLoaded(false)
      return
    }
    let cancelled = false
    setLinkedMetaLoaded(false)
    void (async () => {
      try {
        const loc = await getLocation(substrateLocationId, projectSlug)
        const cid = (loc.stylebook_location_canonical_id ?? "").trim()
        if (!cancelled) {
          setLinkedCanonicalId(cid ? cid : null)
          setLinkedMetaLoaded(true)
        }
      } catch {
        if (!cancelled) {
          setLinkedCanonicalId(null)
          setLinkedMetaLoaded(true)
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [open, substrateLocationId, projectSlug])

  useEffect(() => {
    if (!open || !initialCanonicalId || !projectSlug) {
      setInitialCanonExtra(null)
      return
    }
    if (linkedCanonicalId && initialCanonicalId === linkedCanonicalId) {
      setInitialCanonExtra(null)
      return
    }
    if (suggestions.some((s) => s.canonical_id === initialCanonicalId)) {
      setInitialCanonExtra(null)
      return
    }
    let cancelled = false
    void (async () => {
      try {
        const c = await getCanonicalLocationLegacy(initialCanonicalId, projectSlug)
        if (!cancelled) setInitialCanonExtra(c)
      } catch {
        if (!cancelled) setInitialCanonExtra(null)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [open, initialCanonicalId, projectSlug, suggestions, linkedCanonicalId])

  useEffect(() => {
    if (!open || substrateLocationId == null || !projectSlug) {
      setSuggestions([])
      return
    }
    if (!linkedMetaLoaded) {
      setSuggestions([])
      return
    }
    let cancelled = false
    void (async () => {
      setLoadingSuggestions(true)
      try {
        const res = await getSuggestedCanonicals(projectSlug, substrateLocationId)
        if (!cancelled) {
          const exclude = (linkedCanonicalId ?? "").trim()
          const next = exclude ? res.suggestions.filter((s) => String(s.canonical_id) !== exclude) : res.suggestions
          setSuggestions(next)
        }
      } catch (e) {
        if (!cancelled) {
          setSuggestions([])
          setError(e instanceof Error ? e.message : "Could not load suggestions")
        }
      } finally {
        if (!cancelled) setLoadingSuggestions(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [open, substrateLocationId, projectSlug, linkedMetaLoaded, linkedCanonicalId])

  useEffect(() => {
    if (!open || !projectSlug) return
    if (!linkedMetaLoaded) {
      setSearchHits([])
      setSearchLoading(false)
      return
    }
    const q = searchQ.trim()
    if (!q) {
      setSearchHits([])
      setSearchLoading(false)
      return
    }
    let cancelled = false
    setSearchLoading(true)
    const t = window.setTimeout(() => {
      void (async () => {
        try {
          const res = await listCanonicalLocationsLegacy(projectSlug, q, 20, 0)
          if (!cancelled) {
            const exclude = (linkedCanonicalId ?? "").trim()
            const next = exclude ? res.canonicals.filter((c) => String(c.id) !== exclude) : res.canonicals
            setSearchHits(next)
          }
        } catch {
          if (!cancelled) setSearchHits([])
        } finally {
          if (!cancelled) setSearchLoading(false)
        }
      })()
    }, 300)
    return () => {
      cancelled = true
      window.clearTimeout(t)
    }
  }, [searchQ, open, projectSlug, linkedCanonicalId, linkedMetaLoaded])

  const mergedSuggestions: SuggestedCanonicalItem[] = useMemo(() => {
    const exclude = (linkedCanonicalId ?? "").trim()
    const merged: SuggestedCanonicalItem[] = exclude
      ? suggestions.filter((s) => String(s.canonical_id) !== exclude)
      : [...suggestions]
    if (initialCanonExtra) {
      const exId = initialCanonExtra.id
      if (!exclude || exId !== exclude) {
        if (!merged.some((s) => s.canonical_id === exId)) {
          merged.unshift(canonicalToSuggestedRow(initialCanonExtra))
        }
      }
    }
    if (initialCanonicalId) {
      if (!exclude || initialCanonicalId !== exclude) {
        const ix = merged.findIndex((s) => s.canonical_id === initialCanonicalId)
        if (ix > 0) {
          const [picked] = merged.splice(ix, 1)
          merged.unshift(picked)
        }
      }
    }
    return merged
  }, [suggestions, initialCanonExtra, initialCanonicalId, linkedCanonicalId, linkedMetaLoaded])

  const suggestionRows = useMemo(
    () => suggestedItemsToPickRows(mergedSuggestions),
    [mergedSuggestions],
  )

  const searchRows = useMemo(() => suggestedItemsToPickRows(searchHits.map(canonicalToSuggestedRow)), [
    searchHits,
  ])

  const searchActive = searchQ.trim().length > 0
  const tableRows = searchActive ? searchRows : suggestionRows
  const tableLoading = searchActive ? searchLoading : loadingSuggestions

  async function linkToCanonical(canonicalId: string) {
    if (substrateLocationId == null || !projectSlug) return
    setLinkingCanonicalId(canonicalId)
    setError(null)
    try {
      const pickedLabel =
        tableRows.find((r) => String(r.rowKey) === String(canonicalId))?.location ??
        mergedSuggestions.find((s) => String(s.canonical_id) === String(canonicalId))?.label ??
        searchHits.find((s) => String(s.id) === String(canonicalId))?.label ??
        (initialCanonExtra?.id === canonicalId ? initialCanonExtra.label : canonicalId)
      await linkSubstrateToCanonical(substrateLocationId, projectSlug, canonicalId)
      props.onLinked?.({ id: canonicalId, label: pickedLabel })
      onDone()
      onOpenChange(false)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Link failed")
    } finally {
      setLinkingCanonicalId(null)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[90vh] max-w-3xl flex-col">
        <DialogHeader>
          <DialogTitle>{title ?? "Link to canonical"}</DialogTitle>
          <DialogDescription>
            Search for existing canonicals in{" "}
            <span className="font-semibold text-foreground">{stylebookLabel}</span>
          </DialogDescription>
        </DialogHeader>
        <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-1 py-2 sm:px-2">
          {error ? <p className="text-sm text-destructive">{error}</p> : null}
          <div className="space-y-2">
            <Label htmlFor="canon-search">Search catalog</Label>
            <Input
              id="canon-search"
              placeholder="Type to search canonical labels…"
              value={searchQ}
              onChange={(e) => setSearchQ(e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <div className="text-sm font-medium">{searchActive ? "Search results" : "Suggestions"}</div>
            {tableLoading ? (
              <div className="flex items-center gap-2 py-4 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                {searchActive ? "Searching…" : "Loading…"}
              </div>
            ) : tableRows.length === 0 ? (
              <p className="text-sm text-muted-foreground py-2">
                {searchActive
                  ? "No canonicals match your search."
                  : "No ranked suggestions for this row."}
              </p>
            ) : (
              <div className="max-h-[min(50vh,360px)] overflow-y-auto pr-1">
                <LinkPickTable
                  rows={tableRows}
                  includeAddress={false}
                  busyKey={linkingCanonicalId}
                  linkDisabled={substrateLocationId == null}
                  onLink={(key) => void linkToCanonical(String(key))}
                  linkActionLabel="Link to this canonical"
                />
              </div>
            )}
          </div>
        </div>
        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={linkingCanonicalId !== null}
          >
            Cancel
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
