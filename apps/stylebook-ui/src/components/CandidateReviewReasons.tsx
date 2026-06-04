/** Ingest / policy review context under a candidate row (from ``canonical_review_lines``). */

export function candidateReviewLines(
  candidate: {
    canonical_review_lines?: string[] | null
    defer_display_message?: string | null
  },
): string[] {
  const lines = candidate.canonical_review_lines
  if (Array.isArray(lines) && lines.length > 0) {
    return lines.filter((line): line is string => typeof line === "string" && Boolean(line.trim()))
  }
  const legacy = candidate.defer_display_message
  if (typeof legacy === "string" && legacy.trim()) {
    return [legacy.trim()]
  }
  return []
}

type CandidateReviewReasonsProps = {
  lines: string[]
  className?: string
}

export function CandidateReviewReasons({ lines, className }: CandidateReviewReasonsProps) {
  if (lines.length === 0) return null
  return (
    <div className={className ?? "pl-10 space-y-0.5 max-w-md"}>
      {lines.map((line, index) => (
        <p
          key={`${index}-${line}`}
          className="text-xs text-muted-foreground break-words"
        >
          {line}
        </p>
      ))}
    </div>
  )
}
