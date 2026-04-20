import { useEffect, useState } from "react"
import {
  getCanonicalLocation,
  getSuggestedCanonicals,
  linkSubstrateToCanonical,
  listCanonicalLocations,
  type CanonicalLocation,
  type SuggestedCanonicalItem,
} from "@/lib/api"
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
import { Loader2 } from "lucide-react"

type PickRow = { canonical_id: number; label: string }

export function CanonicalLinkModal(props: {
  open: boolean
  onOpenChange: (open: boolean) => void
  projectSlug: string
  /** Substrate location id (open candidate or linked row for relink/move). */
  substrateLocationId: number | null
  onDone: () => void
  title?: string
  /** When set, pre-select this canonical after loading its label. */
  initialCanonicalId?: number | null
}) {
  const { open, onOpenChange, projectSlug, substrateLocationId, onDone, title, initialCanonicalId } =
    props
  const [suggestions, setSuggestions] = useState<SuggestedCanonicalItem[]>([])
  const [loadingSuggestions, setLoadingSuggestions] = useState(false)
  const [searchQ, setSearchQ] = useState("")
  const [searchLoading, setSearchLoading] = useState(false)
  const [searchHits, setSearchHits] = useState<CanonicalLocation[]>([])
  const [selected, setSelected] = useState<PickRow | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    setSearchQ("")
    setSearchHits([])
    setError(null)
    setSelected(null)
    if (!initialCanonicalId || !projectSlug) {
      return
    }
    let cancelled = false
    void (async () => {
      try {
        const c = await getCanonicalLocation(initialCanonicalId, projectSlug)
        if (!cancelled && c) {
          setSelected({ canonical_id: c.id, label: c.label })
        }
      } catch {
        if (!cancelled) setSelected(null)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [open, substrateLocationId, projectSlug, initialCanonicalId])

  useEffect(() => {
    if (!open || !substrateLocationId || !projectSlug) {
      setSuggestions([])
      return
    }
    let cancelled = false
    void (async () => {
      setLoadingSuggestions(true)
      try {
        const res = await getSuggestedCanonicals(projectSlug, substrateLocationId)
        if (!cancelled) setSuggestions(res.suggestions)
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
  }, [open, substrateLocationId, projectSlug])

  useEffect(() => {
    if (!open || !projectSlug) return
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
          const res = await listCanonicalLocations(projectSlug, q, 20, 0)
          if (!cancelled) setSearchHits(res.canonicals)
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
  }, [searchQ, open, projectSlug])

  async function onConfirm() {
    if (!substrateLocationId || !projectSlug || !selected) return
    setSubmitting(true)
    setError(null)
    try {
      await linkSubstrateToCanonical(
        substrateLocationId,
        projectSlug,
        selected.canonical_id,
      )
      onDone()
      onOpenChange(false)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Link failed")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{title ?? "Link to canonical"}</DialogTitle>
          <DialogDescription>
            Pick a Stylebook canonical. Suggestions use the same retrieval and scoring as ingest;
            search the full catalog by label.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-2">
          {error && <p className="text-sm text-destructive">{error}</p>}
          <div>
            <Label className="text-muted-foreground">Suggestions</Label>
            {loadingSuggestions ? (
              <div className="flex items-center gap-2 py-4 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                Loading…
              </div>
            ) : suggestions.length === 0 ? (
              <p className="text-sm text-muted-foreground py-2">No ranked suggestions for this row.</p>
            ) : (
              <ul className="mt-2 space-y-1 max-h-40 overflow-y-auto border rounded-md p-2">
                {suggestions.map((s) => (
                  <li key={s.canonical_id}>
                    <button
                      type="button"
                      className={`w-full text-left text-sm rounded px-2 py-1.5 hover:bg-muted ${
                        selected?.canonical_id === s.canonical_id ? "bg-muted font-medium" : ""
                      }`}
                      onClick={() =>
                        setSelected({ canonical_id: s.canonical_id, label: s.label })
                      }
                    >
                      {s.label}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div>
            <Label htmlFor="canon-search">Search catalog</Label>
            <Input
              id="canon-search"
              className="mt-1"
              placeholder="Type to search canonical labels…"
              value={searchQ}
              onChange={(e) => setSearchQ(e.target.value)}
            />
            {searchLoading && (
              <p className="text-xs text-muted-foreground mt-1 flex items-center gap-1">
                <Loader2 className="h-3 w-3 animate-spin" />
                Searching…
              </p>
            )}
            {searchHits.length > 0 && (
              <ul className="mt-2 space-y-1 max-h-36 overflow-y-auto border rounded-md p-2">
                {searchHits.map((c) => (
                  <li key={c.id}>
                    <button
                      type="button"
                      className={`w-full text-left text-sm rounded px-2 py-1.5 hover:bg-muted ${
                        selected?.canonical_id === c.id ? "bg-muted font-medium" : ""
                      }`}
                      onClick={() => setSelected({ canonical_id: c.id, label: c.label })}
                    >
                      {c.label}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
          {selected && (
            <p className="text-sm">
              Selected: <span className="font-medium">{selected.label}</span> (#{selected.canonical_id})
            </p>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={submitting}>
            Cancel
          </Button>
          <Button onClick={() => void onConfirm()} disabled={!selected || submitting}>
            {submitting ? "Linking…" : "Link"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
