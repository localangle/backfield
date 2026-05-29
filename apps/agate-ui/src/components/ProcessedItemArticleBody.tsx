import { useEffect, useMemo, useRef, useState, type ReactNode, type RefObject } from 'react'
import { createPortal } from 'react-dom'
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
  /** Stronger highlights for the selected place. */
  highlights: EvidenceSpanRange[]
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
  children,
}: {
  tier: 'ambient' | 'selected'
  anchors: string[]
  onSelectPlace?: (anchor: string) => void
  onOpenDisambiguation: (anchors: string[], clientX: number, clientY: number) => void
  markRef?: RefObject<HTMLElement>
  children: ReactNode
}) {
  const interactive = Boolean(onSelectPlace) && anchors.length > 0

  const handleClick = (e: React.MouseEvent<HTMLElement>) => {
    if (!interactive || !onSelectPlace) return
    e.preventDefault()
    e.stopPropagation()
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
      if (anchors.length === 1) {
        onSelectPlace?.(anchors[0]!)
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
        'rounded-sm px-0.5 text-foreground transition-colors',
        tier === 'selected'
          ? 'border border-transparent bg-amber-200/90 dark:bg-amber-500/40'
          : 'border border-dotted border-yellow-300/70 bg-yellow-100/85 dark:border-yellow-600/45 dark:bg-yellow-500/28',
        interactive && 'cursor-pointer',
        interactive &&
          tier === 'selected' &&
          'hover:bg-amber-300/95 dark:hover:bg-amber-500/55',
        interactive &&
          tier === 'ambient' &&
          'hover:border-yellow-400/80 hover:bg-yellow-200/90 dark:hover:border-yellow-500/55 dark:hover:bg-yellow-500/40',
      )}
    >
      {children}
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
  className,
}: ProcessedItemArticleBodyProps) {
  const firstSelectedMarkRef = useRef<HTMLElement>(null)
  const bodyRef = useRef<HTMLDivElement | null>(null)
  const [disambiguation, setDisambiguation] = useState<DisambiguationMenuState | null>(null)
  const mentionSelectionEnabled = interactionMode === 'normal' || interactionMode === 'select-passage'
  const mentionClickHandler = mentionSelectionEnabled ? onSelectPlace : undefined

  const tieredRanges = useMemo(
    () => mergeTieredHighlightRanges(ambientHighlights, highlights),
    [ambientHighlights, highlights],
  )

  useEffect(() => {
    if (highlights.length === 0 || scrollWhenKey === null || scrollWhenKey === '') {
      return
    }
    const el = firstSelectedMarkRef.current
    if (!el) return
    el.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'nearest' })
  }, [scrollWhenKey, highlights])

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
        {activeTextSelection && onAddPlaceFromSelection ? (
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
    const isFirstSelected = tier === 'selected' && selectedMarkIndex === 0
    const anchors = collectAnchorsForRange(mentionSpanHits, start, end)
    segments.push(
      <StoryMentionMark
        key={`${tier}-${start}-${end}`}
        tier={tier}
        anchors={anchors}
        onSelectPlace={mentionClickHandler}
        onOpenDisambiguation={openDisambiguation}
        markRef={isFirstSelected ? firstSelectedMarkRef : undefined}
      >
        {body.slice(start, end)}
      </StoryMentionMark>,
    )
    if (tier === 'selected') {
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
      {activeTextSelection && onAddPlaceFromSelection ? (
        <AddPlaceSelectionAction
          selection={activeTextSelection}
          label={addPlaceActionLabel}
          onAdd={onAddPlaceFromSelection}
        />
      ) : null}
    </>
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
