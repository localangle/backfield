import { useEffect, useRef, useState } from 'react'
import { Check, Pencil, X } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'

/** Prevent input blur from firing before the adjacent button click runs. */
function preventBlurOnPointerDown(event: React.MouseEvent) {
  event.preventDefault()
}

type InlineNameEditorProps = {
  value: string
  onSave: (next: string) => Promise<void>
  canEdit?: boolean
  /** Shown when ``value`` is blank (e.g. untitled flows). */
  emptyFallback?: string
  ariaLabel: string
  editAriaLabel: string
  saveAriaLabel?: string
  titleClassName?: string
  inputClassName?: string
}

/**
 * Inline title rename: pencil to edit, blur or Enter to save, Escape or X to cancel.
 * Save/cancel buttons use ``mousedown`` prevention so they do not trigger a blur-save.
 */
export function InlineNameEditor({
  value,
  onSave,
  canEdit = true,
  emptyFallback,
  ariaLabel,
  editAriaLabel,
  saveAriaLabel = 'Save name',
  titleClassName = 'text-2xl font-semibold tracking-tight',
  inputClassName = 'min-w-0 flex-1 max-w-xl text-2xl font-semibold h-auto py-2 px-3 tracking-tight',
}: InlineNameEditorProps) {
  const display = value.trim() || emptyFallback || value
  const [editingName, setEditingName] = useState(false)
  const [nameDraft, setNameDraft] = useState(display)
  const [savingName, setSavingName] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!editingName) setNameDraft(display)
  }, [display, editingName])

  useEffect(() => {
    if (editingName) inputRef.current?.focus()
  }, [editingName])

  const cancelNameEdit = () => {
    setNameDraft(display)
    setEditingName(false)
  }

  const saveName = async () => {
    const next = nameDraft.trim()
    if (!next || next === display) {
      cancelNameEdit()
      return
    }
    try {
      setSavingName(true)
      await onSave(next)
      setEditingName(false)
    } catch (error) {
      console.error('Failed to save name:', error)
    } finally {
      setSavingName(false)
    }
  }

  if (!canEdit) {
    return <h1 className={cn(titleClassName)}>{display}</h1>
  }

  if (editingName) {
    return (
      <div className="flex w-full min-w-0 max-w-full flex-nowrap items-center gap-2">
        <Input
          ref={inputRef}
          value={nameDraft}
          onChange={(e) => setNameDraft(e.target.value)}
          onBlur={() => {
            void saveName()
          }}
          onKeyDown={(e) => {
            if (e.key === 'Enter') void saveName()
            if (e.key === 'Escape') cancelNameEdit()
          }}
          disabled={savingName}
          className={cn(inputClassName)}
          aria-label={ariaLabel}
        />
        <Button
          type="button"
          size="icon"
          variant="default"
          className="shrink-0"
          disabled={savingName || !nameDraft.trim()}
          onMouseDown={preventBlurOnPointerDown}
          onClick={() => void saveName()}
          aria-label={saveAriaLabel}
        >
          <Check className="h-4 w-4" />
        </Button>
        <Button
          type="button"
          size="icon"
          variant="outline"
          className="shrink-0"
          disabled={savingName}
          onMouseDown={preventBlurOnPointerDown}
          onClick={cancelNameEdit}
          aria-label="Cancel"
        >
          <X className="h-4 w-4" />
        </Button>
      </div>
    )
  }

  return (
    <div className="inline-flex max-w-full min-h-[2.5rem] items-center gap-2">
      <h1
        className={cn(
          'inline-block min-w-0 max-w-[min(100%,42rem)] truncate',
          titleClassName,
        )}
      >
        {display}
      </h1>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="shrink-0 text-muted-foreground hover:text-foreground"
        onClick={() => {
          setNameDraft(display)
          setEditingName(true)
        }}
        aria-label={editAriaLabel}
      >
        <Pencil className="h-5 w-5" />
      </Button>
    </div>
  )
}
