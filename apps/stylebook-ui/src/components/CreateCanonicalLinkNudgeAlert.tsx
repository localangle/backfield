import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"

type CreateCanonicalLinkNudgeAlertProps = {
  existingLabel: string
  /** e.g. "canonical", "person" */
  entityNoun: string
  onOpenLinkFlow: () => void
  disabled?: boolean
}

export function CreateCanonicalLinkNudgeAlert({
  existingLabel,
  entityNoun,
  onOpenLinkFlow,
  disabled = false,
}: CreateCanonicalLinkNudgeAlertProps) {
  return (
    <Alert className="border-amber-500/40 bg-amber-500/5">
      <AlertTitle className="text-amber-950 dark:text-amber-100">
        A similar {entityNoun} already exists
      </AlertTitle>
      <AlertDescription className="mt-2 space-y-3 text-amber-950/90 dark:text-amber-50/90">
        <p className="text-sm">
          Before creating a new row, consider linking this candidate to{" "}
          <span className="font-medium">{existingLabel}</span> instead.
        </p>
        <Button
          type="button"
          size="sm"
          variant="secondary"
          disabled={disabled}
          onClick={onOpenLinkFlow}
        >
          Open link flow
        </Button>
      </AlertDescription>
    </Alert>
  )
}
