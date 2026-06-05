import { useEffect, useMemo, useState } from "react"
import { LinkPickTable } from "@/components/LinkPickTable"
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
import {
  buildCanonicalLinkExcludeIds,
  isExcludedCanonicalLinkTarget,
} from "@/lib/canonicalLinkModalExclude"
import type { CanonicalLinkModalGenericProps } from "@/lib/entityConfigs/canonicalLinkModalTypes"
import { useSelectedStylebookLabel } from "@/lib/stylebookScopeContext"
import { Loader2 } from "lucide-react"

export function CanonicalLinkModalGeneric<
  TSuggestion extends { canonical_id: string; label: string },
  TCanonical extends { id: string; label: string },
>(props: CanonicalLinkModalGenericProps<TSuggestion, TCanonical>) {
  const {
    open,
    onOpenChange,
    projectSlug,
    stylebookSlug,
    substrateId,
    onDone,
    title,
    initialCanonicalId,
    initialSearchQuery,
    excludeCanonicalId,
    config,
  } = props
  const stylebookLabel = useSelectedStylebookLabel()
  const [suggestions, setSuggestions] = useState<TSuggestion[]>([])
  const [loadingSuggestions, setLoadingSuggestions] = useState(false)
  const [searchQ, setSearchQ] = useState("")
  const [searchLoading, setSearchLoading] = useState(false)
  const [searchHits, setSearchHits] = useState<TCanonical[]>([])
  const [linkingCanonicalId, setLinkingCanonicalId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [initialCanonExtra, setInitialCanonExtra] = useState<TCanonical | null>(null)
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
    if (!open || substrateId == null || !projectSlug) {
      setLinkedCanonicalId(null)
      setLinkedMetaLoaded(false)
      return
    }
    let cancelled = false
    setLinkedMetaLoaded(false)
    void (async () => {
      try {
        const substrate = await config.fetchSubstrate(substrateId, projectSlug)
        const cid = config.getLinkedCanonicalId(substrate)
        if (!cancelled) {
          setLinkedCanonicalId(cid)
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
  }, [open, substrateId, projectSlug, config])

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
        const c = await config.fetchCanonical(initialCanonicalId, stylebookSlug, projectSlug)
        if (!cancelled) setInitialCanonExtra(c)
      } catch {
        if (!cancelled) setInitialCanonExtra(null)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [open, initialCanonicalId, projectSlug, stylebookSlug, suggestions, linkedCanonicalId, config])

  useEffect(() => {
    if (!open || substrateId == null || !projectSlug) {
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
        const res = await config.fetchSuggestions(projectSlug, substrateId)
        if (!cancelled) {
          setSuggestions(
            res.suggestions.filter(
              (s) => !isExcludedCanonicalLinkTarget(s.canonical_id, excludeCanonicalIds),
            ),
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
  }, [open, substrateId, projectSlug, linkedMetaLoaded, excludeCanonicalIds, config])

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
          const res = await config.searchCanonicals(stylebookSlug, q, projectSlug)
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
  }, [searchQ, open, projectSlug, stylebookSlug, excludeCanonicalIds, linkedMetaLoaded, config])

  const mergedSuggestions: TSuggestion[] = useMemo(() => {
    const merged: TSuggestion[] = suggestions.filter(
      (s) => !isExcludedCanonicalLinkTarget(s.canonical_id, excludeCanonicalIds),
    )
    if (initialCanonExtra) {
      const exId = initialCanonExtra.id
      if (!isExcludedCanonicalLinkTarget(exId, excludeCanonicalIds)) {
        if (!merged.some((s) => s.canonical_id === exId)) {
          merged.unshift(config.canonicalToSuggestion(initialCanonExtra))
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
  }, [suggestions, initialCanonExtra, initialCanonicalId, excludeCanonicalIds, config])

  const suggestionRows = useMemo(
    () => mergedSuggestions.map((s) => config.suggestionToPickRow(s)),
    [mergedSuggestions, config],
  )

  const searchRows = useMemo(
    () => searchHits.map((c) => config.suggestionToPickRow(config.canonicalToSuggestion(c))),
    [searchHits, config],
  )

  const searchActive = searchQ.trim().length > 0
  const tableRows = searchActive ? searchRows : suggestionRows
  const tableLoading = searchActive ? searchLoading : loadingSuggestions

  async function linkToCanonical(canonicalId: string) {
    if (substrateId == null || !projectSlug) return
    setLinkingCanonicalId(canonicalId)
    setError(null)
    try {
      const pickedLabel =
        tableRows.find((r) => String(r.rowKey) === String(canonicalId))?.location ??
        mergedSuggestions.find((s) => String(s.canonical_id) === String(canonicalId))?.label ??
        searchHits.find((s) => String(s.id) === String(canonicalId))?.label ??
        (initialCanonExtra?.id === canonicalId ? initialCanonExtra.label : canonicalId)
      await config.linkSubstrate(substrateId, projectSlug, canonicalId)
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
          <DialogTitle>{title ?? config.defaultTitle}</DialogTitle>
          <DialogDescription>
            Search for existing {config.catalogNoun} in{" "}
            <span className="font-semibold text-foreground">{stylebookLabel}</span>
          </DialogDescription>
        </DialogHeader>
        <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-1 py-2 sm:px-2">
          {error ? <p className="text-sm text-destructive">{error}</p> : null}
          <div className="space-y-2">
            <Label htmlFor={config.searchInputId}>{config.searchLabel}</Label>
            <Input
              id={config.searchInputId}
              placeholder={config.searchPlaceholder}
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
                  ? config.emptySearchMessage
                  : "No ranked suggestions for this row."}
              </p>
            ) : (
              <div className="max-h-[min(50vh,360px)] overflow-y-auto pr-1">
                <LinkPickTable
                  rows={tableRows}
                  primaryColumnLabel={config.table.primaryColumnLabel}
                  secondaryColumnLabel={config.table.secondaryColumnLabel}
                  includeAddress={config.table.includeAddress}
                  includeType={config.table.includeType}
                  busyKey={linkingCanonicalId}
                  linkDisabled={substrateId == null}
                  onLink={(key) => void linkToCanonical(String(key))}
                  linkActionLabel={config.linkActionLabel}
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
