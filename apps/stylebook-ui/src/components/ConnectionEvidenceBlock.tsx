import { Badge } from '@/components/ui/badge'
import { formatConnectionEvidence } from '@/lib/connectionEvidence'

interface ConnectionEvidenceBlockProps {
  evidence: Record<string, unknown> | null | undefined
}

export default function ConnectionEvidenceBlock({ evidence }: ConnectionEvidenceBlockProps) {
  const view = formatConnectionEvidence(evidence)
  if (!view) {
    return null
  }

  return (
    <div className="mt-1.5 max-w-xl space-y-1">
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge variant="secondary" className="h-5 px-1.5 text-[11px] font-normal">
          Automatic
        </Badge>
        {view.confidencePercent != null ? (
          <span className="text-[11px] text-muted-foreground tabular-nums">
            {view.confidencePercent}% sure
          </span>
        ) : null}
      </div>
      {view.quote ? (
        <p className="text-xs leading-snug text-muted-foreground border-l-2 border-muted-foreground/25 pl-2">
          {view.quote}
        </p>
      ) : null}
      {view.showReason ? (
        <p className="text-[11px] leading-snug text-muted-foreground/80">{view.reason}</p>
      ) : null}
    </div>
  )
}
