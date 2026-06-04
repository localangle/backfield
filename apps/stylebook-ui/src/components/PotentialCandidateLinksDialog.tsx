import { LinkPickTable, type LinkPickTableRow } from "@/components/LinkPickTable"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Loader2 } from "lucide-react"

type PotentialCandidateLinksDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  canonicalLabel: string
  /** e.g. "locations", "people" */
  candidateNounPlural: string
  loading: boolean
  error: string | null
  rows: LinkPickTableRow[]
  busyKey: string | number | null
  linkDisabled: boolean
  onLink: (rowKey: string | number) => void
  onRefresh: () => void
  linkActionLabel?: string
  primaryColumnLabel?: string
  secondaryColumnLabel?: string
  includeAddress?: boolean
  includeType?: boolean
}

export function PotentialCandidateLinksDialog({
  open,
  onOpenChange,
  canonicalLabel,
  candidateNounPlural,
  loading,
  error,
  rows,
  busyKey,
  linkDisabled,
  onLink,
  onRefresh,
  linkActionLabel,
  primaryColumnLabel = "Name",
  secondaryColumnLabel = "Address",
  includeAddress = true,
  includeType = true,
}: PotentialCandidateLinksDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[min(90vh,720px)] flex flex-col">
        <DialogHeader>
          <DialogTitle>Potential links</DialogTitle>
          <DialogDescription>
            Candidate {candidateNounPlural} that may match{" "}
            <span className="font-medium">{canonicalLabel || "—"}</span>
          </DialogDescription>
        </DialogHeader>
        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto">
          {loading ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin shrink-0" aria-hidden />
              <span>Loading…</span>
            </div>
          ) : error ? (
            <p className="text-sm text-destructive">{error}</p>
          ) : rows.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No candidates in this list. Use Refresh if the queue has changed, or close when you
              are done.
            </p>
          ) : (
            <div className="max-h-[min(56vh,420px)] overflow-y-auto pr-1">
              <LinkPickTable
                rows={rows}
                busyKey={busyKey}
                linkDisabled={linkDisabled}
                onLink={onLink}
                linkActionLabel={linkActionLabel}
                primaryColumnLabel={primaryColumnLabel}
                secondaryColumnLabel={secondaryColumnLabel}
                includeAddress={includeAddress}
                includeType={includeType}
              />
            </div>
          )}
        </div>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onRefresh} disabled={loading}>
            Refresh
          </Button>
          <Button type="button" onClick={() => onOpenChange(false)}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
