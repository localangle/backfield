import { useCallback, useRef, useState, type DragEvent, type ReactNode } from 'react'

import { cn } from '@/lib/utils'

interface JsonFileDropZoneProps {
  disabled?: boolean
  onFiles: (files: File[]) => void | Promise<void>
  children?: ReactNode
}

function isJsonFileName(name: string): boolean {
  return name.toLowerCase().endsWith('.json')
}

export default function JsonFileDropZone({
  disabled,
  onFiles,
  children,
}: JsonFileDropZoneProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragOver, setDragOver] = useState(false)

  const takeFiles = useCallback(
    async (list: FileList | File[] | null) => {
      if (!list || disabled) return
      const files = Array.from(list).filter((file) => isJsonFileName(file.name))
      if (files.length === 0) return
      await onFiles(files)
    },
    [disabled, onFiles],
  )

  const onDragEnter = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    event.stopPropagation()
    if (!disabled) setDragOver(true)
  }

  const onDragOver = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    event.stopPropagation()
    if (!disabled) setDragOver(true)
  }

  const onDragLeave = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    event.stopPropagation()
    setDragOver(false)
  }

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    event.stopPropagation()
    setDragOver(false)
    void takeFiles(event.dataTransfer.files)
  }

  return (
    <div
      className={cn(
        'rounded-md border border-dashed border-muted-foreground/40 bg-muted/20 p-3 transition-colors',
        dragOver && !disabled && 'border-primary bg-primary/5',
        disabled && 'opacity-60',
      )}
      onDragEnter={onDragEnter}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".json,application/json"
        multiple
        className="sr-only"
        disabled={disabled}
        onChange={(event) => {
          void takeFiles(event.target.files)
          event.target.value = ''
        }}
      />
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-muted-foreground">
          Drop JSON files here, or choose files to add. Up to 20 files.
        </p>
        <button
          type="button"
          className="inline-flex h-9 shrink-0 items-center justify-center rounded-md border border-input bg-background px-3 text-sm font-medium hover:bg-accent hover:text-accent-foreground disabled:pointer-events-none disabled:opacity-50"
          disabled={disabled}
          onClick={() => inputRef.current?.click()}
        >
          Choose files
        </button>
      </div>
      {children}
    </div>
  )
}
