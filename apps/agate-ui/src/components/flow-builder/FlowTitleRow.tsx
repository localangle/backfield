import { forwardRef } from 'react'

import { InlineNameEditor, type InlineNameEditorHandle } from '@/components/InlineNameEditor'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'

export type FlowTitleRowHandle = InlineNameEditorHandle

type FlowTitleRowProps = {
  name: string
  /** Blur/confirm rename (run view and project headers). */
  onSave?: (nextName: string) => Promise<void>
  /** Live updates while typing (flow builder create/edit header). */
  onChange?: (nextName: string) => void
  /** Always show a text field when editable — required for Save flow to read the current title. */
  alwaysEditable?: boolean
  canEdit?: boolean
}

/** Flow title display + rename UI. */
export const FlowTitleRow = forwardRef<FlowTitleRowHandle, FlowTitleRowProps>(
  function FlowTitleRow(
    { name, onSave, onChange, alwaysEditable = false, canEdit = true },
    ref,
  ) {
    const display = name.trim() || 'Untitled flow'

    if (!canEdit) {
      return (
        <h1 className="text-2xl font-bold leading-tight tracking-tight truncate max-w-[min(100%,42rem)]">
          {display}
        </h1>
      )
    }

    if (alwaysEditable && onChange) {
      return (
        <Input
          value={name}
          onChange={(event) => onChange(event.target.value)}
          placeholder="Untitled flow"
          aria-label="Flow name"
          className={cn(
            'h-auto min-w-0 max-w-xl border-0 bg-transparent px-0 py-0',
            'text-2xl font-bold leading-tight tracking-tight shadow-none',
            'placeholder:text-muted-foreground/70 focus-visible:ring-0 focus-visible:ring-offset-0',
          )}
        />
      )
    }

    if (!onSave) {
      return (
        <h1 className="text-2xl font-bold leading-tight tracking-tight truncate max-w-[min(100%,42rem)]">
          {display}
        </h1>
      )
    }

    return (
      <InlineNameEditor
        ref={ref}
        value={name}
        onSave={onSave}
        canEdit={canEdit}
        compact
        emptyFallback="Untitled flow"
        ariaLabel="Flow name"
        editAriaLabel="Edit flow name"
        saveAriaLabel="Save flow name"
        titleClassName="text-2xl font-bold leading-tight tracking-tight"
        inputClassName="h-auto min-w-0 max-w-xl flex-1 px-3 py-1.5 text-2xl font-bold leading-tight tracking-tight"
      />
    )
  },
)
