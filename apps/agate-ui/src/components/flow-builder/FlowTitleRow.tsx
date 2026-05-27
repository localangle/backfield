import { useEffect, useRef, useState } from 'react'
import { Check, Pencil, X } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

type FlowTitleRowProps = {
  name: string
  onSave: (nextName: string) => Promise<void>
  canEdit?: boolean
}

/** Flow title display + rename UI (matches workspace name editing). */
export function FlowTitleRow({ name, onSave, canEdit = true }: FlowTitleRowProps) {
  const display = name.trim() || 'Untitled flow'
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
      console.error('Failed to save flow name:', error)
    } finally {
      setSavingName(false)
    }
  }

  if (!canEdit) {
    return <h1 className="text-2xl font-bold tracking-tight">{display}</h1>
  }

  if (editingName) {
    return (
      <div className="flex w-full min-w-0 max-w-full flex-nowrap items-center gap-2">
        <Input
          ref={inputRef}
          value={nameDraft}
          onChange={(e) => setNameDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') void saveName()
            if (e.key === 'Escape') cancelNameEdit()
          }}
          disabled={savingName}
          className="h-auto min-w-0 max-w-xl flex-1 px-3 py-2 text-2xl font-bold tracking-tight"
          aria-label="Flow name"
        />
        <Button
          type="button"
          size="icon"
          variant="default"
          className="shrink-0"
          disabled={savingName || !nameDraft.trim()}
          onClick={() => void saveName()}
          aria-label="Save flow name"
        >
          <Check className="h-4 w-4" />
        </Button>
        <Button
          type="button"
          size="icon"
          variant="outline"
          className="shrink-0"
          disabled={savingName}
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
      <h1 className="inline-block min-w-0 max-w-[min(100%,42rem)] truncate text-2xl font-bold tracking-tight">
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
        aria-label="Edit flow name"
      >
        <Pencil className="h-5 w-5" />
      </Button>
    </div>
  )
}
