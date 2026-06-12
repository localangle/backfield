import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'

type FlowDescriptionFieldProps = {
  value: string
  onChange: (value: string) => void
  /** When set, blur saves the trimmed description (existing flows). */
  onBlurSave?: (value: string) => Promise<void>
  canEdit?: boolean
  className?: string
}

/** Optional flow description shown below the title on create/edit screens. */
export function FlowDescriptionField({
  value,
  onChange,
  onBlurSave,
  canEdit = true,
  className,
}: FlowDescriptionFieldProps) {
  const trimmed = value.trim()

  if (!canEdit) {
    if (!trimmed) return null
    return (
      <p className={cn('max-w-2xl text-sm text-muted-foreground whitespace-pre-wrap', className)}>
        {trimmed}
      </p>
    )
  }

  return (
    <Textarea
      value={value}
      onChange={(event) => onChange(event.target.value)}
      onBlur={() => {
        if (!onBlurSave) return
        void onBlurSave(value.trim())
      }}
      placeholder="Describe what this flow does (optional)"
      rows={1}
      className={cn(
        'h-auto min-h-0 max-w-2xl resize-none border-0 bg-transparent px-0 py-0 text-sm leading-snug text-muted-foreground shadow-none',
        'placeholder:text-muted-foreground/70 focus-visible:ring-0 focus-visible:ring-offset-0',
        className,
      )}
      aria-label="Flow description"
    />
  )
}

export function flowDescriptionTableText(description: string | null | undefined): string {
  const trimmed = (description ?? '').trim()
  return trimmed || '—'
}
