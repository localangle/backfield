import { Link } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { CheckCircle2, Loader2, X } from "lucide-react"

type CandidateQueueCreatedToastProps = {
  title: string
  canonicalHref: string
  canonicalLabel: string
  leaving: boolean
  followupCheckingMessage: string
  followupLoading: boolean
  followupError: string | null
  hasPotentialLinks: boolean
  onOpenPotentialLinks: () => void
  onDismiss: () => void
}

export function CandidateQueueCreatedToast({
  title,
  canonicalHref,
  canonicalLabel,
  leaving,
  followupCheckingMessage,
  followupLoading,
  followupError,
  hasPotentialLinks,
  onOpenPotentialLinks,
  onDismiss,
}: CandidateQueueCreatedToastProps) {
  return (
    <div className="fixed bottom-6 right-6 z-50 w-max max-w-[calc(100vw-3rem)]">
      <div
        role="status"
        className={cn(
          "rounded-xl border border-primary/25 bg-card text-card-foreground shadow-xl ring-2 ring-primary/15 transition-opacity duration-300",
          leaving ? "opacity-0" : "opacity-100",
        )}
      >
        <div className="flex items-start gap-3 p-4 pr-2">
          <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-primary" aria-hidden />
          <div className="flex min-w-0 max-w-[min(28rem,calc(100vw-5.5rem))] flex-col gap-1.5">
            <div className="text-sm font-semibold leading-none">{title}</div>
            <div className="text-sm text-muted-foreground">
              Saved as{" "}
              <Link
                to={canonicalHref}
                className="font-medium text-foreground underline-offset-4 hover:underline break-words"
              >
                {canonicalLabel}
              </Link>
            </div>
            {followupLoading ? (
              <div className="flex items-center gap-2 text-xs text-muted-foreground pt-0.5">
                <Loader2 className="h-3.5 w-3.5 animate-spin shrink-0" aria-hidden />
                <span>{followupCheckingMessage}</span>
              </div>
            ) : null}
            {followupError && !followupLoading ? (
              <p className="text-xs text-destructive">{followupError}</p>
            ) : null}
            {hasPotentialLinks ? (
              <Button
                type="button"
                size="sm"
                className="mt-1 w-full shrink-0 self-start sm:w-auto"
                onClick={onOpenPotentialLinks}
              >
                Potential links found
              </Button>
            ) : null}
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
    </div>
  )
}
