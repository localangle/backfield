import { Link } from "react-router-dom"
import type { SimilarCanonicalMatch } from "@/lib/useSimilarCanonicalNotice"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"

interface SimilarCanonicalNoticeProps {
  /** Plural noun for the title, e.g. "locations". */
  entityNounPlural: string
  matches: SimilarCanonicalMatch[]
  canEdit: boolean
  /** Match id currently being merged, disables that row's button. */
  mergingId: string | null
  onMerge: (match: SimilarCanonicalMatch) => void
  onIgnore: () => void
  detailHref: (canonicalId: string) => string
}

export function SimilarCanonicalNotice({
  entityNounPlural,
  matches,
  canEdit,
  mergingId,
  onMerge,
  onIgnore,
  detailHref,
}: SimilarCanonicalNoticeProps) {
  if (matches.length === 0) return null
  return (
    <Alert className="border-amber-500/40 bg-amber-500/5">
      <AlertTitle className="text-amber-950 dark:text-amber-100">
        Similar {entityNounPlural} may exist
      </AlertTitle>
      <AlertDescription className="mt-2 space-y-3 text-amber-950/90 dark:text-amber-50/90">
        <p className="text-sm">
          This record may be a duplicate. Open a match to compare, or merge this record into it.
        </p>
        <div className="space-y-2">
          {matches.map((match) => (
            <div
              key={match.id}
              className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-amber-500/30 bg-background/60 px-3 py-2"
            >
              <Link
                to={detailHref(match.id)}
                className="min-w-0 break-words text-sm font-medium text-primary hover:underline"
              >
                {match.label}
              </Link>
              {canEdit ? (
                <Button
                  type="button"
                  size="sm"
                  variant="secondary"
                  className="shrink-0"
                  disabled={mergingId !== null}
                  onClick={() => onMerge(match)}
                >
                  {mergingId === match.id ? "Merging…" : "Merge into this"}
                </Button>
              ) : null}
            </div>
          ))}
        </div>
        <Button type="button" size="sm" variant="outline" onClick={onIgnore}>
          Ignore
        </Button>
      </AlertDescription>
    </Alert>
  )
}
