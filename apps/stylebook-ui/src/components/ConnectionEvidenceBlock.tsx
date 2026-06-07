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
    <div className="mt-2 rounded-md border bg-muted/30 px-3 py-2 text-sm space-y-1.5">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
        <span>{view.sourceLabel}</span>
        {view.confidenceLabel ? <span>· {view.confidenceLabel}</span> : null}
      </div>
      {view.quote ? (
        <blockquote className="border-l-2 border-border pl-3 text-sm italic text-foreground/90">
          {view.quote}
        </blockquote>
      ) : null}
      {view.reason && view.reason !== view.quote ? (
        <p className="text-xs text-muted-foreground">{view.reason}</p>
      ) : null}
    </div>
  )
}
