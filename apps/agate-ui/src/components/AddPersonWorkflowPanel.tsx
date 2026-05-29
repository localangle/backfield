import { useEffect, useRef, useState } from 'react'
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
import { PERSON_NATURE_OPTIONS, personNatureDisplayLabel } from '@/lib/personMentionNature'
import { newUserPersonId } from '@/lib/review/entities/person/reviewRow'
import {
  createSavedPersonFromArticleEvidence,
  type CreatedSavedPersonFromArticleEvidence,
} from '@/lib/stylebookPeopleApi'
import { Loader2 } from 'lucide-react'

export type AddPersonWorkflowCreatedPayload = {
  anchor: string
  name: string
  personType: string
  title: string
  affiliation: string
  nature: string
  publicFigure: boolean
  mentionText: string
  roleInStory: string
  selection: ArticleTextSelection
  created?: CreatedSavedPersonFromArticleEvidence
}

export interface AddPersonWorkflowPanelProps {
  projectSlug: string
  runId: string
  articleId: number
  persistToStylebook: boolean
  selection: ArticleTextSelection
  /** When true, the user is picking a new story passage; form fields stay as-is. */
  awaitingNewSelection?: boolean
  onChangeSelection: () => void
  onCancel: () => void
  onCreated: (payload: AddPersonWorkflowCreatedPayload) => void
  onError: (message: string, title?: string) => void
}

export function AddPersonWorkflowPanel({
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
}: AddPersonWorkflowPanelProps) {
  const [name, setName] = useState('')
  const [personType, setPersonType] = useState('')
  const [title, setTitle] = useState('')
  const [affiliation, setAffiliation] = useState('')
  const [nature, setNature] = useState('other')
  const [publicFigure, setPublicFigure] = useState(false)
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

  const ready =
    !awaitingNewSelection &&
    name.trim().length > 0 &&
    mentionText.trim().length > 0 &&
    selection.text.trim().length > 0 &&
    (!persistToStylebook || (articleId > 0 && projectSlug.trim().length > 0))

  const saveTextStep = async () => {
    if (!ready || saving) return
    if (persistToStylebook) {
      if (!projectSlug.trim()) {
        onError('This project is not set up for saving people.', 'Could not save')
        return
      }
      if (articleId <= 0) {
        onError('This story is not ready for saving people yet.', 'Could not save')
        return
      }
    }
    setSaving(true)
    try {
      const trimmedName = name.trim()
      const trimmedType = personType.trim()
      const trimmedMention = mentionText.trim()
      const trimmedTitle = title.trim()
      const trimmedAffiliation = affiliation.trim()
      const trimmedRole = roleInStory.trim()
      const trimmedNature = nature.trim() || 'other'
      if (persistToStylebook) {
        const created = await createSavedPersonFromArticleEvidence(projectSlug, {
          article_id: articleId,
          run_id: runId,
          name: trimmedName,
          person_type: trimmedType || null,
          title: trimmedTitle || null,
          affiliation: trimmedAffiliation || null,
          public_figure: publicFigure,
          nature: trimmedNature,
          mention_text: trimmedMention,
          quote_text: selection.text,
          start_char: selection.start,
          end_char: selection.end,
          role_in_story: trimmedRole || null,
        })
        onCreated({
          anchor: created.anchor,
          name: trimmedName,
          personType: trimmedType,
          title: trimmedTitle,
          affiliation: trimmedAffiliation,
          nature: trimmedNature,
          publicFigure,
          mentionText: trimmedMention,
          roleInStory: trimmedRole,
          selection,
          created,
        })
      } else {
        onCreated({
          anchor: newUserPersonId(),
          name: trimmedName,
          personType: trimmedType,
          title: trimmedTitle,
          affiliation: trimmedAffiliation,
          nature: trimmedNature,
          publicFigure,
          mentionText: trimmedMention,
          roleInStory: trimmedRole,
          selection,
        })
      }
    } catch (e) {
      onError(
        e instanceof Error ? e.message : 'We could not save this person. Try again.',
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
            <h3 className="text-sm font-semibold text-foreground">Add person</h3>
            <p className="mt-1 text-xs text-muted-foreground">
              Add details from the selected story passage.
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
          <Label htmlFor="add-person-name">Name</Label>
          <Input
            id="add-person-name"
            value={name}
            disabled={saving}
            onChange={(e) => setName(e.target.value)}
            placeholder="Person name"
          />
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="add-person-type">Type</Label>
          <Input
            id="add-person-type"
            value={personType}
            disabled={saving}
            onChange={(e) => setPersonType(e.target.value)}
            placeholder="e.g. politician, athlete"
          />
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="add-person-title">Title</Label>
          <Input
            id="add-person-title"
            value={title}
            disabled={saving}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Job or role"
          />
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="add-person-affiliation">Affiliation</Label>
          <Input
            id="add-person-affiliation"
            value={affiliation}
            disabled={saving}
            onChange={(e) => setAffiliation(e.target.value)}
            placeholder="Organization or context"
          />
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="add-person-nature">Nature</Label>
          <Select value={nature} disabled={saving} onValueChange={setNature}>
            <SelectTrigger id="add-person-nature" className="h-9 w-full">
              <SelectValue placeholder="Select nature" />
            </SelectTrigger>
            <SelectContent>
              {PERSON_NATURE_OPTIONS.map((value) => (
                <SelectItem key={value} value={value}>
                  {personNatureDisplayLabel(value)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="add-person-mention">Mention in the story</Label>
          <Input
            id="add-person-mention"
            value={mentionText}
            disabled={saving}
            onChange={(e) => setMentionText(e.target.value)}
            placeholder="Words that name this person"
          />
        </div>

        {!persistToStylebook ? (
          <p className="text-xs text-muted-foreground">
            This person is saved with this review only. They are not added to your people catalog
            until this story is linked to a saved article.
          </p>
        ) : null}

        <div className="space-y-1.5">
          <Label htmlFor="add-person-role">Role in story</Label>
          <Textarea
            id="add-person-role"
            value={roleInStory}
            disabled={saving}
            rows={3}
            onChange={(e) => setRoleInStory(e.target.value)}
            placeholder="Why this person matters in the story"
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
            'Add person'
          )}
        </Button>
      </div>
    </div>
  )
}
