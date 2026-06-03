import { Link } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { CheckCircle2, X } from "lucide-react"

type CandidateQueueLinkedToastProps = {
  title: string
  candidateLabel: string
  canonicalHref: string
  canonicalLabel: string
  leaving: boolean
  onDismiss: () => void
}

export function CandidateQueueLinkedToast({
  title,
  candidateLabel,
  canonicalHref,
  canonicalLabel,
  leaving,
  onDismiss,
}: CandidateQueueLinkedToastProps) {
  return (
    <div className="fixed bottom-6 right-6 z-50 w-max max-w-[calc(100vw-3rem)]">
      <div
        role="status"
        className={cn(
          "rounded-xl border border-primary/25 bg-card text-card-foreground shadow-xl ring-2 ring-primary/15 transition-opacity duration-300 p-4 flex items-start gap-3",
          leaving ? "opacity-0" : "opacity-100",
        )}
      >
        <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-primary" aria-hidden />
        <div className="text-sm min-w-0 max-w-[min(28rem,calc(100vw-5.5rem))]">
          <div className="font-semibold leading-none">{title}</div>
          <div className="text-muted-foreground mt-1">
            <span className="font-medium text-foreground break-words">{candidateLabel}</span> →{" "}
            <Link
              to={canonicalHref}
              className="font-medium text-foreground underline-offset-4 hover:underline break-words"
            >
              {canonicalLabel}
            </Link>
          </div>
        </div>
        <Button
          type="button"
          size="icon"
          variant="ghost"
          className="-mr-1 -mt-1 h-8 w-8 shrink-0"
          onClick={onDismiss}
          aria-label="Dismiss"
        >
          <X className="h-4 w-4" />
        </Button>
      </div>
    </div>
  )
}
