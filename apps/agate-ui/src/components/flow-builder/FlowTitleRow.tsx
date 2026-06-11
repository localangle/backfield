import { InlineNameEditor } from '@/components/InlineNameEditor'

type FlowTitleRowProps = {
  name: string
  onSave: (nextName: string) => Promise<void>
  canEdit?: boolean
}

/** Flow title display + rename UI (matches workspace/project name editing). */
export function FlowTitleRow({ name, onSave, canEdit = true }: FlowTitleRowProps) {
  return (
    <InlineNameEditor
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
}
