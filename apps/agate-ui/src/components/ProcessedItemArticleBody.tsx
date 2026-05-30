import { useEffect, useMemo, useRef, useState, type ReactNode, type RefObject } from 'react'
import { createPortal } from 'react-dom'
import { X } from 'lucide-react'
import {
  collectAnchorsForRange,
  mergeTieredHighlightRanges,
  type EvidenceSpanRange,
  type MentionSpanHit,
} from '@/lib/review/content/evidenceSpan'
import { cn } from '@/lib/utils'

export interface ProcessedItemArticleBodyProps {
  body: string
  /** Subtle highlights for every geocoded mention (``original_text``) before / besides selection. */
  ambientHighlights?: EvidenceSpanRange[]
  /** Stronger highlights for the selected place or person mentions (non-quotes). */
  highlights: EvidenceSpanRange[]
  /** Distinct highlights for attributed quotes when reviewing people. */
  quoteHighlights?: EvidenceSpanRange[]
  /**
   * Changes to this value (e.g. selected place id) scroll the first selected highlight into view when
   * ``highlights`` is non-empty.
   */
  scrollWhenKey: string | null
  /** Per-place mention ranges with anchor ids (for click / disambiguation). */
  mentionSpanHits?: MentionSpanHit[]
  /** Display labels keyed by place anchor (popup when one span maps to several places). */
  placeLabels?: Record<string, string>
  /** Select a geocoded place from a story mention click. */
  onSelectPlace?: (anchor: string) => void
  /** When ``select-passage``, only text selection works. When ``locked``, the story pane is read-only. */
  interactionMode?: 'normal' | 'select-passage' | 'locked'
  /** Disambiguation menu heading when one span maps to several anchors. */
  mentionChoicePrompt?: string
  /** Report ordinary text selections so callers can start an add workflow. */
  onTextSelectionChange?: (selection: ArticleTextSelection | null) => void
  activeTextSelection?: ArticleTextSelection | null
  onAddPlaceFromSelection?: (selection: ArticleTextSelection) => void
  addPlaceActionLabel?: string
  /** People edit: map ``start:end`` span keys to occurrence client ids. */
  editableOccurrenceClientIds?: Record<string, string>
  selectedOccurrenceClientId?: string | null
  onSelectOccurrenceClientId?: (clientId: string) => void
  onRemoveOccurrenceClientId?: (clientId: string) => void
  onAddOccurrenceFromSelection?: (selection: ArticleTextSelection, kind: 'mention' | 'quote') => void
  className?: string
}

export type ArticleTextSelection = {
  start: number
  end: number
  text: string
  rect: { left: number; top: number; width: number; height: number }
}

type DisambiguationMenuState = {
  anchors: string[]
  x: number
  y: number
}

function MentionDisambiguationMenu({
  anchors,
  labels,
  position,
  prompt,
  onSelect,
  onClose,
}: {
  anchors: string[]
  labels: Record<string, string>
  position: { x: number; y: number }
  prompt: string
  onSelect: (anchor: string) => void
  onClose: () => void
}) {
  const menuRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    const onPointerDown = (e: PointerEvent) => {
      const target = e.target
      if (!(target instanceof Node)) return
      if (menuRef.current?.contains(target)) return
      onClose()
    }
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('pointerdown', onPointerDown, true)
    window.addEventListener('keydown', onKeyDown)
    return () => {
      window.removeEventListener('pointerdown', onPointerDown, true)
      window.removeEventListener('keydown', onKeyDown)
    }
  }, [onClose])

  return createPortal(
    <div
      ref={menuRef}
      role="menu"
      aria-label={prompt}
      className="fixed z-[200] min-w-[11rem] max-w-[16rem] rounded-md border bg-popover p-1 text-popover-foreground shadow-md"
      style={{ left: position.x, top: position.y }}
    >
      <p className="px-2 py-1 text-[11px] font-medium text-muted-foreground">{prompt}</p>
      {anchors.map((anchor) => (
        <button
          key={anchor}
          type="button"
          role="menuitem"
          className="flex w-full cursor-pointer rounded-sm px-2 py-1.5 text-left text-sm outline-none hover:bg-accent focus:bg-accent"
          onClick={() => {
            onSelect(anchor)
            onClose()
          }}
        >
          {labels[anchor]?.trim() || anchor}
        </button>
      ))}
    </div>,
    document.body,
  )
}

function StoryMentionMark({
  tier,
  anchors,
  onSelectPlace,
  onOpenDisambiguation,
  markRef,
  editableOccurrenceClientId,
  occurrenceSelected = false,
  onSelectOccurrence,
  onRemoveOccurrence,
  children,
}: {
  tier: 'ambient' | 'selected' | 'quote'
  anchors: string[]
  onSelectPlace?: (anchor: string) => void
  onOpenDisambiguation: (anchors: string[], clientX: number, clientY: number) => void
  markRef?: RefObject<HTMLElement>
  editableOccurrenceClientId?: string
  occurrenceSelected?: boolean
  onSelectOccurrence?: (clientId: string) => void
  onRemoveOccurrence?: (clientId: string) => void
  children: ReactNode
}) {
  const editable = Boolean(editableOccurrenceClientId && onSelectOccurrence)
  const interactive = editable || (Boolean(onSelectPlace) && anchors.length > 0)

  const handleClick = (e: React.MouseEvent<HTMLElement>) => {
    if (!interactive) return
    e.preventDefault()
    e.stopPropagation()
    if (editable && editableOccurrenceClientId) {
      onSelectOccurrence?.(editableOccurrenceClientId)
      return
    }
    if (!onSelectPlace) return
    if (anchors.length === 1) {
      onSelectPlace(anchors[0]!)
      return
    }
    onOpenDisambiguation(anchors, e.clientX, e.clientY)
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLElement>) => {
    if (!interactive) return
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      if (editable && editableOccurrenceClientId) {
        onSelectOccurrence?.(editableOccurrenceClientId)
        return
      }
      if (!onSelectPlace) return
      if (anchors.length === 1) {
        onSelectPlace(anchors[0]!)
        return
      }
      const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
      onOpenDisambiguation(anchors, rect.left, rect.bottom + 4)
    }
  }

  return (
    <mark
      ref={markRef}
      role={interactive ? 'button' : undefined}
      tabIndex={interactive ? 0 : undefined}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
      className={cn(
        'relative rounded-sm px-0.5 text-foreground transition-colors',
        tier === 'quote'
          ? 'border border-transparent bg-sky-200/90 dark:bg-sky-500/40'
          : tier === 'selected'
            ? 'border border-transparent bg-amber-200/90 dark:bg-amber-500/40'
            : 'border border-dotted border-yellow-300/70 bg-yellow-100/85 dark:border-yellow-600/45 dark:bg-yellow-500/28',
        occurrenceSelected && 'ring-2 ring-inset ring-primary',
        editable && 'inline-flex items-center gap-1',
        editable && 'group',
        interactive && 'cursor-pointer',
        interactive &&
          tier === 'quote' &&
          'hover:bg-sky-200/95 dark:hover:bg-sky-500/45',
        interactive &&
          tier === 'selected' &&
          'hover:bg-amber-300/95 dark:hover:bg-amber-500/55',
        interactive &&
          tier === 'ambient' &&
          'hover:border-yellow-400/80 hover:bg-yellow-200/90 dark:hover:border-yellow-500/55 dark:hover:bg-yellow-500/40',
      )}
      title={tier === 'quote' ? 'Quote' : tier === 'selected' ? 'Mention' : undefined}
    >
      {children}
      {editable && editableOccurrenceClientId && onRemoveOccurrence ? (
        <button
          type="button"
          aria-label="Remove highlight"
          className={cn(
            'inline-grid h-5 w-5 shrink-0 place-items-center self-center rounded-full border border-border bg-background p-0 text-muted-foreground shadow-sm hover:bg-destructive hover:text-destructive-foreground',
            occurrenceSelected
              ? 'inline-grid'
              : 'hidden group-hover:inline-grid group-focus-within:inline-grid',
          )}
          onMouseDown={(e) => {
            e.preventDefault()
            e.stopPropagation()
          }}
          onClick={(e) => {
            e.preventDefault()
            e.stopPropagation()
            onRemoveOccurrence(editableOccurrenceClientId)
          }}
        >
          <X className="size-2.5 shrink-0" strokeWidth={2.5} aria-hidden />
        </button>
      ) : null}
    </mark>
  )
}

/**
 * Renders article text with optional ambient + selected highlight ranges.
 */
export function ProcessedItemArticleBody({
  body,
  ambientHighlights = [],
  highlights,
  quoteHighlights = [],
  scrollWhenKey,
  mentionSpanHits = [],
  placeLabels = {},
  onSelectPlace,
  interactionMode = 'normal',
  mentionChoicePrompt = 'Which place?',
  onTextSelectionChange,
  activeTextSelection = null,
  onAddPlaceFromSelection,
  addPlaceActionLabel = 'Add place',
  editableOccurrenceClientIds,
  selectedOccurrenceClientId = null,
  onSelectOccurrenceClientId,
  onRemoveOccurrenceClientId,
  onAddOccurrenceFromSelection,
  className,
}: ProcessedItemArticleBodyProps) {
  const firstSelectedMarkRef = useRef<HTMLElement>(null)
  const bodyRef = useRef<HTMLDivElement | null>(null)
  const [disambiguation, setDisambiguation] = useState<DisambiguationMenuState | null>(null)
  const mentionSelectionEnabled = interactionMode === 'normal' || interactionMode === 'select-passage'
  const mentionClickHandler = mentionSelectionEnabled ? onSelectPlace : undefined

  const tieredRanges = useMemo(
    () => mergeTieredHighlightRanges(ambientHighlights, highlights, quoteHighlights),
    [ambientHighlights, highlights, quoteHighlights],
  )

  useEffect(() => {
    const hasHighlights = highlights.length > 0 || quoteHighlights.length > 0
    if (!hasHighlights || scrollWhenKey === null || scrollWhenKey === '') {
      return
    }
    const el = firstSelectedMarkRef.current
    if (!el) return
    el.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'nearest' })
  }, [scrollWhenKey, highlights, quoteHighlights])

  const openDisambiguation = (anchors: string[], clientX: number, clientY: number) => {
    setDisambiguation({ anchors, x: clientX, y: clientY })
  }

  const readTextSelection = () => {
    if (!onTextSelectionChange || !mentionSelectionEnabled) return
    const root = bodyRef.current
    const sel = window.getSelection()
    if (!root || !sel || sel.rangeCount === 0 || sel.isCollapsed) {
      onTextSelectionChange(null)
      return
    }
    const range = sel.getRangeAt(0)
    if (!root.contains(range.startContainer) || !root.contains(range.endContainer)) {
      onTextSelectionChange(null)
      return
    }
    const before = range.cloneRange()
    before.selectNodeContents(root)
    before.setEnd(range.startContainer, range.startOffset)
    const start = before.toString().length
    const text = range.toString()
    const end = start + text.length
    if (!text.trim() || start < 0 || end <= start || end > body.length) {
      onTextSelectionChange(null)
      return
    }
    const rect = range.getBoundingClientRect()
    onTextSelectionChange({
      start,
      end,
      text,
      rect: { left: rect.left, top: rect.top, width: rect.width, height: rect.height },
    })
  }

  if (tieredRanges.length === 0) {
    return (
      <>
        <div
          ref={bodyRef}
          onMouseUp={readTextSelection}
          onKeyUp={readTextSelection}
          className={cn(
            'whitespace-pre-wrap font-sans text-sm leading-relaxed text-foreground',
            className,
          )}
        >
          {body}
        </div>
        {activeTextSelection && onAddOccurrenceFromSelection ? (
          <AddOccurrenceSelectionAction
            selection={activeTextSelection}
            onAdd={onAddOccurrenceFromSelection}
          />
        ) : null}
        {activeTextSelection && onAddPlaceFromSelection && !onAddOccurrenceFromSelection ? (
          <AddPlaceSelectionAction
            selection={activeTextSelection}
            label={addPlaceActionLabel}
            onAdd={onAddPlaceFromSelection}
          />
        ) : null}
      </>
    )
  }

  const segments: ReactNode[] = []
  let cursor = 0
  let selectedMarkIndex = 0

  for (const { start, end, tier } of tieredRanges) {
    if (!Number.isFinite(start) || !Number.isFinite(end) || start < cursor || end <= start || end > body.length) {
      continue
    }
    if (start > cursor) {
      segments.push(body.slice(cursor, start))
    }
    const isFirstSelected =
      (tier === 'selected' || tier === 'quote') && selectedMarkIndex === 0
    const anchors = collectAnchorsForRange(mentionSpanHits, start, end)
    const spanKey = `${start}:${end}`
    const editableOccurrenceClientId =
      (tier === 'selected' || tier === 'quote') && editableOccurrenceClientIds
        ? editableOccurrenceClientIds[spanKey]
        : undefined
    segments.push(
      <StoryMentionMark
        key={`${tier}-${start}-${end}`}
        tier={tier}
        anchors={anchors}
        onSelectPlace={mentionClickHandler}
        onOpenDisambiguation={openDisambiguation}
        markRef={isFirstSelected ? firstSelectedMarkRef : undefined}
        editableOccurrenceClientId={editableOccurrenceClientId}
        occurrenceSelected={
          Boolean(
            editableOccurrenceClientId &&
              selectedOccurrenceClientId &&
              editableOccurrenceClientId === selectedOccurrenceClientId,
          )
        }
        onSelectOccurrence={onSelectOccurrenceClientId}
        onRemoveOccurrence={onRemoveOccurrenceClientId}
      >
        {body.slice(start, end)}
      </StoryMentionMark>,
    )
    if (tier === 'selected' || tier === 'quote') {
      selectedMarkIndex += 1
    }
    cursor = end
  }

  if (cursor < body.length) {
    segments.push(body.slice(cursor))
  }

  return (
    <>
      <div
        ref={bodyRef}
        onMouseUp={readTextSelection}
        onKeyUp={readTextSelection}
        className={cn(
          'whitespace-pre-wrap font-sans text-sm leading-relaxed text-foreground',
          className,
        )}
      >
        {segments}
      </div>
      {disambiguation ? (
        <MentionDisambiguationMenu
          anchors={disambiguation.anchors}
          labels={placeLabels}
          position={{ x: disambiguation.x, y: disambiguation.y }}
          prompt={mentionChoicePrompt}
          onSelect={(anchor) => mentionClickHandler?.(anchor)}
          onClose={() => setDisambiguation(null)}
        />
      ) : null}
      {activeTextSelection && onAddOccurrenceFromSelection ? (
        <AddOccurrenceSelectionAction
          selection={activeTextSelection}
          onAdd={onAddOccurrenceFromSelection}
        />
      ) : null}
      {activeTextSelection && onAddPlaceFromSelection && !onAddOccurrenceFromSelection ? (
        <AddPlaceSelectionAction
          selection={activeTextSelection}
          label={addPlaceActionLabel}
          onAdd={onAddPlaceFromSelection}
        />
      ) : null}
    </>
  )
}

function AddOccurrenceSelectionAction({
  selection,
  onAdd,
}: {
  selection: ArticleTextSelection
  onAdd: (selection: ArticleTextSelection, kind: 'mention' | 'quote') => void
}) {
  const top = Math.max(8, selection.rect.top - 44)
  const left = Math.max(8, selection.rect.left + selection.rect.width / 2 - 72)
  return createPortal(
    <div
      className="fixed z-[210] flex gap-1 rounded-md border bg-popover p-1 text-popover-foreground shadow-md"
      style={{ left, top }}
      onMouseDown={(e) => e.preventDefault()}
    >
      <button
        type="button"
        className="rounded-sm px-2 py-1 text-xs font-medium hover:bg-accent focus:outline-none focus:ring-2 focus:ring-ring"
        onClick={() => onAdd(selection, 'mention')}
      >
        Add mention
      </button>
      <button
        type="button"
        className="rounded-sm px-2 py-1 text-xs font-medium hover:bg-accent focus:outline-none focus:ring-2 focus:ring-ring"
        onClick={() => onAdd(selection, 'quote')}
      >
        Add quote
      </button>
    </div>,
    document.body,
  )
}

function AddPlaceSelectionAction({
  selection,
  label,
  onAdd,
}: {
  selection: ArticleTextSelection
  label: string
  onAdd: (selection: ArticleTextSelection) => void
}) {
  const top = Math.max(8, selection.rect.top - 38)
  const left = Math.max(8, selection.rect.left + selection.rect.width / 2 - 44)
  return createPortal(
    <button
      type="button"
      className="fixed z-[210] rounded-md border bg-popover px-2.5 py-1.5 text-xs font-medium text-popover-foreground shadow-md hover:bg-accent focus:outline-none focus:ring-2 focus:ring-ring"
      style={{ left, top }}
      onMouseDown={(e) => e.preventDefault()}
      onClick={() => onAdd(selection)}
    >
      {label}
    </button>,
    document.body,
  )
}
