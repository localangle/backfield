import { Textarea } from "@/components/ui/textarea"
import { cn } from "@/lib/utils"
import { StickyNote } from "lucide-react"

type CandidateQueueInlineNoteProps = {
  candidateId: number
  savedNoteText: string
  isEditing: boolean
  draft: string
  saving: boolean
  disabled: boolean
  onOpenEditor: () => void
  onDraftChange: (value: string) => void
  onSave: () => void
  onCancelEdit: () => void
}

export function CandidateQueueInlineNote({
  candidateId,
  savedNoteText,
  isEditing,
  draft,
  saving,
  disabled,
  onOpenEditor,
  onDraftChange,
  onSave,
  onCancelEdit,
}: CandidateQueueInlineNoteProps) {
  return (
    <div className="border-t border-border/60 pt-3 mt-3">
      <div className="text-sm font-medium">Note</div>
      {isEditing ? (
        <div className="mt-2 space-y-2">
          <Textarea
            rows={4}
            value={draft}
            disabled={disabled || saving}
            onChange={(e) => onDraftChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && !saving) {
                e.preventDefault()
                onCancelEdit()
                onSave()
              } else if (e.key === "Escape") {
                e.preventDefault()
                onCancelEdit()
              }
            }}
            onBlur={() => {
              onCancelEdit()
              onSave()
            }}
            autoFocus
            placeholder="Add a brief note…"
            id={`candidate-note-${candidateId}`}
          />
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <StickyNote className="h-3.5 w-3.5" aria-hidden />
            <span>Click outside to save. Cmd/Ctrl+Enter saves.</span>
            {saving ? <span>Saving…</span> : null}
          </div>
        </div>
      ) : (
        <button
          type="button"
          className={cn(
            "mt-2 w-full rounded-md border border-border/60 bg-background/60 p-3 text-left text-sm transition-colors",
            "hover:bg-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
          )}
          disabled={disabled || saving}
          onClick={onOpenEditor}
        >
          {savedNoteText ? (
            <p className="whitespace-pre-wrap">{savedNoteText}</p>
          ) : (
            <p className="text-muted-foreground italic">Click to add a note…</p>
          )}
        </button>
      )}
    </div>
  )
}
