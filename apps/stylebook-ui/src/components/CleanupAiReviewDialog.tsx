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
import { listCleanupAiModels, startCleanupAiReview, type CleanupAiModel } from "@/lib/api"

type CleanupAiReviewDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  stylebookSlug: string
  checkId: string
  onReviewStarted: (reviewId: string) => void
}

export function CleanupAiReviewDialog({
  open,
  onOpenChange,
  stylebookSlug,
  checkId,
  onReviewStarted,
}: CleanupAiReviewDialogProps) {
  const [models, setModels] = useState<CleanupAiModel[]>([])
  const [loadingModels, setLoadingModels] = useState(false)
  const [selectedModelId, setSelectedModelId] = useState<string>("")
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open || !stylebookSlug) return
    let cancelled = false
    setLoadingModels(true)
    setError(null)
    void listCleanupAiModels(stylebookSlug)
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
    if (!selectedModel) return
    setStarting(true)
    setError(null)
    try {
      const review = await startCleanupAiReview({
        stylebookSlug,
        checkId,
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
            Choose a model to review all duplicate clusters in this check. Suggestions appear when
            the review finishes; you can accept or reject each one.
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
            <label className="text-sm font-medium" htmlFor="cleanup-ai-model">
              Model
            </label>
            <Select value={selectedModelId} onValueChange={setSelectedModelId}>
              <SelectTrigger id="cleanup-ai-model">
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
            disabled={starting || loadingModels || !selectedModel}
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
