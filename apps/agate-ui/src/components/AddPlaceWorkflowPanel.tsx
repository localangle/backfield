import { useEffect, useMemo, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import type { ArticleTextSelection } from '@/components/ProcessedItemArticleBody'
import {
  PLACE_EXTRACT_LOCATION_TYPES,
  placeExtractTypeLabel,
  sortPlaceExtractTypeOptions,
} from '@/lib/placeExtractTypeLabel'
import { newUserPlaceId } from '@/lib/review/entities/location/placeGeometry'
import {
  createSavedPlaceFromArticleEvidence,
  type CreatedSavedPlaceFromArticleEvidence,
} from '@/lib/stylebookLocationsApi'
import { Loader2 } from 'lucide-react'

export type AddPlaceWorkflowCreatedPayload = {
  anchor: string
  label: string
  locationType: string
  mentionText: string
  roleInStory: string
  selection: ArticleTextSelection
  /** Present when the place was also saved to Stylebook from article evidence. */
  created?: CreatedSavedPlaceFromArticleEvidence
}

export interface AddPlaceWorkflowPanelProps {
  projectSlug: string
  runId: string
  articleId: number
  /** When false, the place is stored in the review overlay only (no Stylebook row). */
  persistToStylebook: boolean
  selection: ArticleTextSelection
  /** When true, the user is picking a new story passage; form fields stay as-is. */
  awaitingNewSelection?: boolean
  onChangeSelection: () => void
  onCancel: () => void
  onCreated: (payload: AddPlaceWorkflowCreatedPayload) => void
  onError: (message: string, title?: string) => void
}

export function AddPlaceWorkflowPanel({
  projectSlug,
  runId,
  articleId,
  persistToStylebook,
  selection,
  awaitingNewSelection = false,
  onChangeSelection,
  onCancel,
  onCreated,
  onError,
}: AddPlaceWorkflowPanelProps) {
  const [label, setLabel] = useState('')
  const [locationType, setLocationType] = useState('')
  const [mentionText, setMentionText] = useState(() => selection.text.trim())
  const [roleInStory, setRoleInStory] = useState('')
  const [saving, setSaving] = useState(false)
  const previousSelectionRef = useRef(selection)

  useEffect(() => {
    const previous = previousSelectionRef.current
    if (
      previous.start === selection.start &&
      previous.end === selection.end &&
      previous.text === selection.text
    ) {
      return
    }
    setMentionText((current) => {
      const previousDefault = previous.text.trim()
      if (current.trim() === previousDefault) {
        return selection.text.trim()
      }
      return current
    })
    previousSelectionRef.current = selection
  }, [selection])

  const typeOptions = useMemo(
    () => sortPlaceExtractTypeOptions(PLACE_EXTRACT_LOCATION_TYPES),
    [],
  )
  const ready =
    !awaitingNewSelection &&
    label.trim().length > 0 &&
    locationType.trim().length > 0 &&
    mentionText.trim().length > 0 &&
    selection.text.trim().length > 0 &&
    (!persistToStylebook || (articleId > 0 && projectSlug.trim().length > 0))

  const saveTextStep = async () => {
    if (!ready || saving) return
    if (persistToStylebook) {
      if (!projectSlug.trim()) {
        onError('This project is not set up for saving places.', 'Could not save')
        return
      }
      if (articleId <= 0) {
        onError('This story is not ready for saving places yet.', 'Could not save')
        return
      }
    }
    setSaving(true)
    try {
      const trimmedLabel = label.trim()
      const trimmedType = locationType.trim()
      const trimmedMention = mentionText.trim()
      const trimmedRole = roleInStory.trim()
      if (persistToStylebook) {
        const created = await createSavedPlaceFromArticleEvidence(projectSlug, {
          article_id: articleId,
          run_id: runId,
          label: trimmedLabel,
          location_type: trimmedType,
          mention_text: trimmedMention,
          quote_text: selection.text,
          start_char: selection.start,
          end_char: selection.end,
          role_in_story: trimmedRole || null,
        })
        onCreated({
          anchor: created.anchor,
          label: trimmedLabel,
          locationType: trimmedType,
          created,
          mentionText: trimmedMention,
          roleInStory: trimmedRole,
          selection,
        })
      } else {
        onCreated({
          anchor: newUserPlaceId(),
          label: trimmedLabel,
          locationType: trimmedType,
          mentionText: trimmedMention,
          roleInStory: trimmedRole,
          selection,
        })
      }
    } catch (e) {
      onError(
        e instanceof Error ? e.message : 'We could not save this place. Try again.',
        'Could not save',
      )
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col overflow-hidden rounded-lg border border-primary/30 bg-card">
      <div className="shrink-0 border-b border-border p-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold text-foreground">Add place</h3>
            <p className="mt-1 text-xs text-muted-foreground">
              Add details from the selected story passage, then find it on the map.
            </p>
          </div>
          <Button type="button" variant="ghost" size="sm" onClick={onCancel} disabled={saving}>
            Close
          </Button>
        </div>
      </div>
      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-3">
        <div className="rounded-md border bg-muted/30 p-2.5">
          <div className="flex items-center justify-between gap-2">
            <Label className="text-xs font-medium text-muted-foreground">Selected passage</Label>
            <Button
              type="button"
              variant="link"
              size="sm"
              className="h-auto p-0 text-xs"
              onClick={onChangeSelection}
              disabled={saving}
            >
              Change selection
            </Button>
          </div>
          <p className="mt-1 max-h-32 overflow-y-auto whitespace-pre-wrap text-sm text-foreground">
            {awaitingNewSelection ? (
              <span className="text-muted-foreground">
                Highlight a new passage in the story to replace this selection.
              </span>
            ) : (
              selection.text
            )}
          </p>
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="add-place-label">Place name</Label>
          <Input
            id="add-place-label"
            value={label}
            disabled={saving}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="Name this place"
          />
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="add-place-type">Type</Label>
          <Select value={locationType} disabled={saving} onValueChange={setLocationType}>
            <SelectTrigger id="add-place-type" className="h-9 w-full">
              <SelectValue placeholder="Choose a type" />
            </SelectTrigger>
            <SelectContent>
              {typeOptions.map((slug) => (
                <SelectItem key={slug} value={slug}>
                  {placeExtractTypeLabel(slug)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="add-place-mention">Mention in the story</Label>
          <Input
            id="add-place-mention"
            value={mentionText}
            disabled={saving}
            onChange={(e) => setMentionText(e.target.value)}
            placeholder="Words that name the place"
          />
        </div>

        {!persistToStylebook ? (
          <p className="text-xs text-muted-foreground">
            This place is saved with this review only. It is not added to your location catalog
            until this story is linked to a saved article.
          </p>
        ) : null}

        <div className="space-y-1.5">
          <Label htmlFor="add-place-role">Role in story</Label>
          <Textarea
            id="add-place-role"
            value={roleInStory}
            disabled={saving}
            rows={3}
            onChange={(e) => setRoleInStory(e.target.value)}
            placeholder="Why this place matters in the story"
          />
        </div>
      </div>
      <div className="flex shrink-0 items-center justify-between gap-2 border-t border-border p-3">
        <Button type="button" variant="outline" onClick={onCancel} disabled={saving}>
          Cancel
        </Button>
        <Button type="button" onClick={() => void saveTextStep()} disabled={!ready || saving}>
          {saving ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              Saving…
            </>
          ) : (
            'Continue to map'
          )}
        </Button>
      </div>
    </div>
  )
}
