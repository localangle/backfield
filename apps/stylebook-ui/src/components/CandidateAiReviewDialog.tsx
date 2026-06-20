import { useEffect, useMemo, useState } from "react"
import { Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  listCandidateAiModels,
  startCandidateAiReview,
  type CandidateAiModel,
  type CandidateAiReviewEntityType,
} from "@/lib/api"

type CandidateAiReviewDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  stylebookSlug: string
  projectSlug: string
  entityType: CandidateAiReviewEntityType
  onReviewStarted: (reviewId: string) => void
}

export function CandidateAiReviewDialog({
  open,
  onOpenChange,
  stylebookSlug,
  projectSlug,
  entityType,
  onReviewStarted,
}: CandidateAiReviewDialogProps) {
  const [models, setModels] = useState<CandidateAiModel[]>([])
  const [loadingModels, setLoadingModels] = useState(false)
  const [selectedModelId, setSelectedModelId] = useState<string>("")
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open || !stylebookSlug) return
    let cancelled = false
    setLoadingModels(true)
    setError(null)
    void listCandidateAiModels(stylebookSlug)
      .then((response) => {
        if (cancelled) return
        setModels(response.models)
        if (response.models.length > 0) {
          setSelectedModelId(response.models[0].id)
        }
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setError(err instanceof Error ? err.message : "Failed to load models")
      })
      .finally(() => {
        if (!cancelled) setLoadingModels(false)
      })
    return () => {
      cancelled = true
    }
  }, [open, stylebookSlug])

  const selectedModel = useMemo(
    () => models.find((model) => model.id === selectedModelId) ?? null,
    [models, selectedModelId],
  )

  async function handleStart() {
    if (!selectedModel || !projectSlug) return
    setStarting(true)
    setError(null)
    try {
      const review = await startCandidateAiReview({
        stylebookSlug,
        entityType,
        projectSlug,
        providerModelId: selectedModel.provider_model_id,
        aiModelConfigId: selectedModel.id,
      })
      onReviewStarted(review.id)
      onOpenChange(false)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to start AI review")
    } finally {
      setStarting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Review with AI</DialogTitle>
          <DialogDescription>
            Choose a model to review open queue items and suggest whether to link, create, or
            defer each one. Recommendations appear on rows as the review progresses.
          </DialogDescription>
        </DialogHeader>
        {loadingModels ? (
          <div className="flex items-center gap-2 text-muted-foreground py-4">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading models…
          </div>
        ) : models.length === 0 ? (
          <p className="text-sm text-muted-foreground py-2">
            No active text models are configured for this organization.
          </p>
        ) : (
          <div className="space-y-2">
            <label className="text-sm font-medium" htmlFor="candidate-ai-model">
              Model
            </label>
            <Select value={selectedModelId} onValueChange={setSelectedModelId}>
              <SelectTrigger id="candidate-ai-model">
                <SelectValue placeholder="Select a model" />
              </SelectTrigger>
              <SelectContent>
                {models.map((model) => (
                  <SelectItem key={model.id} value={model.id}>
                    {model.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}
        {error ? <p className="text-sm text-destructive">{error}</p> : null}
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            type="button"
            disabled={starting || loadingModels || !selectedModel || !projectSlug}
            onClick={() => void handleStart()}
          >
            {starting ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
                Starting…
              </>
            ) : (
              "Start review"
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
