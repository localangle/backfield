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
import { ORGANIZATION_NATURE_OPTIONS, organizationNatureDisplayLabel } from '@/lib/organizationMentionNature'
import {
  organizationTypeManualSelectOptions,
  placeExtractTypeLabel,
} from '@/lib/placeExtractTypeLabel'
import { newUserOrganizationId } from '@/lib/review/entities/organization/reviewRow'
import {
  createSavedOrganizationFromArticleEvidence,
  type CreatedSavedOrganizationFromArticleEvidence,
} from '@/lib/stylebookOrganizationsApi'
import { Loader2 } from 'lucide-react'

const ADD_ORGANIZATION_TYPE_NONE = '__none__'

export type AddOrganizationWorkflowCreatedPayload = {
  anchor: string
  name: string
  organizationType: string
  nature: string
  mentionText: string
  roleInStory: string
  selection: ArticleTextSelection
  created?: CreatedSavedOrganizationFromArticleEvidence
}

export interface AddOrganizationWorkflowPanelProps {
  projectSlug: string
  runId: string
  articleId: number
  persistToStylebook: boolean
  selection: ArticleTextSelection
  awaitingNewSelection?: boolean
  onChangeSelection: () => void
  onCancel: () => void
  onCreated: (payload: AddOrganizationWorkflowCreatedPayload) => void
  onError: (message: string, title?: string) => void
}

export function AddOrganizationWorkflowPanel({
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
}: AddOrganizationWorkflowPanelProps) {
  const [name, setName] = useState('')
  const [organizationType, setOrganizationType] = useState('')
  const [nature, setNature] = useState('other')
  const [mentionText, setMentionText] = useState(() => selection.text.trim())
  const [roleInStory, setRoleInStory] = useState('')
  const [saving, setSaving] = useState(false)
  const previousSelectionRef = useRef(selection)
  const typeOptions = useMemo(
    () => organizationTypeManualSelectOptions(organizationType),
    [organizationType],
  )

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
        onError('This project is not set up for saving organizations.', 'Could not save')
        return
      }
      if (articleId <= 0) {
        onError('This story is not ready for saving organizations yet.', 'Could not save')
        return
      }
    }
    setSaving(true)
    try {
      const trimmedName = name.trim()
      const trimmedType = organizationType.trim()
      const trimmedMention = mentionText.trim()
      const trimmedRole = roleInStory.trim()
      const trimmedNature = nature.trim() || 'other'
      if (persistToStylebook) {
        const created = await createSavedOrganizationFromArticleEvidence(projectSlug, {
          article_id: articleId,
          run_id: runId,
          name: trimmedName,
          organization_type: trimmedType || null,
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
          organizationType: trimmedType,
          nature: trimmedNature,
          mentionText: trimmedMention,
          roleInStory: trimmedRole,
          selection,
          created,
        })
      } else {
        onCreated({
          anchor: newUserOrganizationId(),
          name: trimmedName,
          organizationType: trimmedType,
          nature: trimmedNature,
          mentionText: trimmedMention,
          roleInStory: trimmedRole,
          selection,
        })
      }
    } catch (e) {
      onError(
        e instanceof Error ? e.message : 'We could not save this organization. Try again.',
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
            <h3 className="text-sm font-semibold text-foreground">Add organization</h3>
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
          <Label htmlFor="add-organization-name">Name</Label>
          <Input
            id="add-organization-name"
            value={name}
            disabled={saving}
            onChange={(e) => setName(e.target.value)}
            placeholder="Organization name"
          />
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="add-organization-type">Type</Label>
          <Select
            value={organizationType || ADD_ORGANIZATION_TYPE_NONE}
            disabled={saving}
            onValueChange={(value) =>
              setOrganizationType(value === ADD_ORGANIZATION_TYPE_NONE ? '' : value)
            }
          >
            <SelectTrigger id="add-organization-type" className="h-9 w-full">
              <SelectValue placeholder="Select type" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ADD_ORGANIZATION_TYPE_NONE}>None</SelectItem>
              {typeOptions.map((value) => (
                <SelectItem key={value} value={value}>
                  {placeExtractTypeLabel(value)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="add-organization-nature">Nature</Label>
          <Select value={nature} disabled={saving} onValueChange={setNature}>
            <SelectTrigger id="add-organization-nature" className="h-9 w-full">
              <SelectValue placeholder="Select nature" />
            </SelectTrigger>
            <SelectContent>
              {ORGANIZATION_NATURE_OPTIONS.map((value) => (
                <SelectItem key={value} value={value}>
                  {organizationNatureDisplayLabel(value)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="add-organization-mention">Mention in the story</Label>
          <Input
            id="add-organization-mention"
            value={mentionText}
            disabled={saving}
            onChange={(e) => setMentionText(e.target.value)}
            placeholder="Words that name this organization"
          />
        </div>

        {!persistToStylebook ? (
          <p className="text-xs text-muted-foreground">
            This organization is saved with this review only. It is not added to your catalog until
            this story is linked to a saved article.
          </p>
        ) : null}

        <div className="space-y-1.5">
          <Label htmlFor="add-organization-role">Role in story</Label>
          <Textarea
            id="add-organization-role"
            value={roleInStory}
            disabled={saving}
            rows={3}
            onChange={(e) => setRoleInStory(e.target.value)}
            placeholder="Why this organization matters in the story"
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
            'Add organization'
          )}
        </Button>
      </div>
    </div>
  )
}
