import { useEffect, useMemo, useState } from "react"
import {
  getCanonicalPerson,
  getPerson,
  getSuggestedPersonCanonicals,
  linkPersonSubstrateToCanonical,
  listCanonicalPeople,
  type CanonicalPerson,
  type SuggestedPersonCanonicalItem,
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
import {
  buildCanonicalLinkExcludeIds,
  isExcludedCanonicalLinkTarget,
} from "@/lib/canonicalLinkModalExclude"
import { useSelectedStylebookLabel } from "@/lib/stylebookScopeContext"
import { Loader2 } from "lucide-react"

function canonicalToSuggestedRow(c: CanonicalPerson): SuggestedPersonCanonicalItem {
  return {
    canonical_id: c.id,
    label: c.label,
    person_type: c.person_type ?? null,
    title: c.title ?? null,
    affiliation: c.affiliation ?? null,
  }
}

function personSuggestionDetailLine(s: SuggestedPersonCanonicalItem): string {
  const parts = [(s.title ?? "").trim(), (s.affiliation ?? "").trim()].filter(Boolean)
  return parts.length > 0 ? parts.join(" · ") : "—"
}

function suggestedItemsToPickRows(items: SuggestedPersonCanonicalItem[]): LinkPickTableRow[] {
  return items.map((s) => ({
    rowKey: s.canonical_id,
    location: s.label,
    typeLabel:
      s.person_type && String(s.person_type).trim()
        ? placeExtractTypeLabel(s.person_type)
        : "—",
    address: personSuggestionDetailLine(s),
  }))
}

export function PersonCanonicalLinkModal(props: {
  open: boolean
  onOpenChange: (open: boolean) => void
  projectSlug: string
  stylebookSlug: string
  substratePersonId: number | null
  onDone: () => void
  onLinked?: (canonical: { id: string; label: string }) => void
  title?: string
  initialCanonicalId?: string | null
  /** Pre-fills catalog search when the modal opens (e.g. candidate display name). */
  initialSearchQuery?: string | null
  /** Omit from suggestions/search (e.g. canonical detail page the move was started from). */
  excludeCanonicalId?: string | null
}) {
  const {
    open,
    onOpenChange,
    projectSlug,
    stylebookSlug,
    substratePersonId,
    onDone,
    title,
    initialCanonicalId,
    initialSearchQuery,
    excludeCanonicalId,
  } = props
  const stylebookLabel = useSelectedStylebookLabel()
  const [suggestions, setSuggestions] = useState<SuggestedPersonCanonicalItem[]>([])
  const [loadingSuggestions, setLoadingSuggestions] = useState(false)
  const [searchQ, setSearchQ] = useState("")
  const [searchLoading, setSearchLoading] = useState(false)
  const [searchHits, setSearchHits] = useState<CanonicalPerson[]>([])
  const [linkingCanonicalId, setLinkingCanonicalId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [initialCanonExtra, setInitialCanonExtra] = useState<CanonicalPerson | null>(null)
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
      return
    }
    const prefill = (initialSearchQuery ?? "").trim()
    if (prefill) {
      setSearchQ(prefill)
    }
  }, [open, initialSearchQuery])

  useEffect(() => {
    if (!open || substratePersonId == null || !projectSlug) {
      setLinkedCanonicalId(null)
      setLinkedMetaLoaded(false)
      return
    }
    let cancelled = false
    setLinkedMetaLoaded(false)
    void (async () => {
      try {
        const row = await getPerson(substratePersonId, projectSlug)
        const cid = (row.stylebook_person_canonical_id ?? "").trim()
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
  }, [open, substratePersonId, projectSlug])

  const excludeCanonicalIds = useMemo(
    () => buildCanonicalLinkExcludeIds(linkedCanonicalId, excludeCanonicalId),
    [linkedCanonicalId, excludeCanonicalId],
  )

  useEffect(() => {
    if (!open || !initialCanonicalId || !projectSlug || !stylebookSlug) {
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
        const c = await getCanonicalPerson(initialCanonicalId, stylebookSlug, projectSlug)
        if (!cancelled) setInitialCanonExtra(c)
      } catch {
        if (!cancelled) setInitialCanonExtra(null)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [open, initialCanonicalId, projectSlug, stylebookSlug, suggestions, linkedCanonicalId])

  useEffect(() => {
    if (!open || substratePersonId == null || !projectSlug) {
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
        const res = await getSuggestedPersonCanonicals(projectSlug, substratePersonId)
        if (!cancelled) {
          setSuggestions(
            res.suggestions.filter((s) => !isExcludedCanonicalLinkTarget(s.canonical_id, excludeCanonicalIds)),
          )
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
  }, [open, substratePersonId, projectSlug, linkedMetaLoaded, excludeCanonicalIds])

  useEffect(() => {
    if (!open || !projectSlug || !stylebookSlug) return
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
          const res = await listCanonicalPeople(stylebookSlug, q, 20, 0, undefined, projectSlug)
          if (!cancelled) {
            setSearchHits(
              res.canonicals.filter((c) => !isExcludedCanonicalLinkTarget(c.id, excludeCanonicalIds)),
            )
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
  }, [searchQ, open, projectSlug, stylebookSlug, excludeCanonicalIds, linkedMetaLoaded])

  const mergedSuggestions: SuggestedPersonCanonicalItem[] = useMemo(() => {
    const merged: SuggestedPersonCanonicalItem[] = suggestions.filter(
      (s) => !isExcludedCanonicalLinkTarget(s.canonical_id, excludeCanonicalIds),
    )
    if (initialCanonExtra) {
      const exId = initialCanonExtra.id
      if (!isExcludedCanonicalLinkTarget(exId, excludeCanonicalIds)) {
        if (!merged.some((s) => s.canonical_id === exId)) {
          merged.unshift(canonicalToSuggestedRow(initialCanonExtra))
        }
      }
    }
    if (initialCanonicalId) {
      if (!isExcludedCanonicalLinkTarget(initialCanonicalId, excludeCanonicalIds)) {
        const ix = merged.findIndex((s) => s.canonical_id === initialCanonicalId)
        if (ix > 0) {
          const [picked] = merged.splice(ix, 1)
          merged.unshift(picked)
        }
      }
    }
    return merged
  }, [suggestions, initialCanonExtra, initialCanonicalId, excludeCanonicalIds])

  const suggestionRows = useMemo(
    () => suggestedItemsToPickRows(mergedSuggestions),
    [mergedSuggestions],
  )

  const searchRows = useMemo(
    () => suggestedItemsToPickRows(searchHits.map(canonicalToSuggestedRow)),
    [searchHits],
  )

  const searchActive = searchQ.trim().length > 0
  const tableRows = searchActive ? searchRows : suggestionRows
  const tableLoading = searchActive ? searchLoading : loadingSuggestions

  async function linkToCanonical(canonicalId: string) {
    if (substratePersonId == null || !projectSlug) return
    setLinkingCanonicalId(canonicalId)
    setError(null)
    try {
      const pickedLabel =
        tableRows.find((r) => String(r.rowKey) === String(canonicalId))?.location ??
        mergedSuggestions.find((s) => String(s.canonical_id) === String(canonicalId))?.label ??
        searchHits.find((s) => String(s.id) === String(canonicalId))?.label ??
        (initialCanonExtra?.id === canonicalId ? initialCanonExtra.label : canonicalId)
      await linkPersonSubstrateToCanonical(substratePersonId, projectSlug, canonicalId)
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
          <DialogTitle>{title ?? "Link to canonical person"}</DialogTitle>
          <DialogDescription>
            Search for existing people in{" "}
            <span className="font-semibold text-foreground">{stylebookLabel}</span>
          </DialogDescription>
        </DialogHeader>
        <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-1 py-2 sm:px-2">
          {error ? <p className="text-sm text-destructive">{error}</p> : null}
          <div className="space-y-2">
            <Label htmlFor="person-canon-search">Search Stylebook</Label>
            <Input
              id="person-canon-search"
              placeholder="Type to search names…"
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
                  ? "No people match your search."
                  : "No ranked suggestions for this row."}
              </p>
            ) : (
              <div className="max-h-[min(50vh,360px)] overflow-y-auto pr-1">
                <LinkPickTable
                  rows={tableRows}
                  primaryColumnLabel="Name"
                  secondaryColumnLabel="Affiliation"
                  includeAddress
                  includeType={false}
                  busyKey={linkingCanonicalId}
                  linkDisabled={substratePersonId == null}
                  onLink={(key) => void linkToCanonical(String(key))}
                  linkActionLabel="Link to this person"
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
