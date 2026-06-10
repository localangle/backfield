import { useEffect, useMemo, useRef, useState } from 'react'
import { ChevronRight } from 'lucide-react'

import { cn } from '@/lib/utils'
import {
  categoryHeading,
  type CompatibleNodeEntry,
  type CompatibleNextNodesResult,
} from '@/lib/nodeCompatibility'

type AddNodeChooserProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  compatibility: CompatibleNextNodesResult
  onSelect: (type: string) => void
  anchorRect: { top: number; right: number; bottom: number; left: number } | null
}

type FlatRow = CompatibleNodeEntry & { rowKey: string }
type Group = { category: string; heading: string; rows: FlatRow[] }

const MENU_WIDTH_PX = 340
const MENU_MAX_HEIGHT_PX = 360
const MENU_PLACEMENT_HEIGHT_PX = 180
const MENU_GAP_PX = 8

/** Placeholder chooser blurbs until product copy replaces them. */
const NODE_CHOOSER_BLURBS: Record<string, string> = {
  ArticleMetadata: 'Consectetur adipiscing elit sed do eiusmod tempor incididunt ut labore.',
  EmbedText: 'Excepteur sint occaecat cupidatat non proident sunt in culpa.',
  GeocodeAgent: 'Duis aute irure dolor in reprehenderit in voluptate velit.',
  OrganizationExtract: 'Ut enim ad minim veniam, quis nostrud exercitation ullamco.',
  PersonExtract: 'Sed do eiusmod tempor incididunt ut labore et dolore magna.',
  PlaceExtract: 'Lorem ipsum dolor sit amet, consectetur adipiscing elit.',
}

function chooserBlurb(row: CompatibleNodeEntry): string {
  const placeholder = NODE_CHOOSER_BLURBS[row.type]
  if (placeholder) return placeholder
  const fromMeta = row.description.trim()
  return fromMeta !== '' ? fromMeta : 'Lorem ipsum dolor sit amet.'
}

const SIMPLE_CATEGORY_LABELS: Record<string, string> = {
  extraction: 'Extract',
  embedding: 'Embed',
  enrichment: 'Enrich',
  geography: 'Enrich',
  filter: 'Transform',
  review: 'Transform',
  text: 'Transform',
}

const CATEGORY_ORDER = ['Extract', 'Embed', 'Enrich', 'Transform']

function groupRows(rows: FlatRow[]): Group[] {
  const byCategory = new Map<string, FlatRow[]>()
  for (const row of rows) {
    const heading = SIMPLE_CATEGORY_LABELS[row.category] ?? categoryHeading(row.category)
    const list = byCategory.get(heading) ?? []
    list.push(row)
    byCategory.set(heading, list)
  }
  return [...byCategory.entries()]
    .sort(([a], [b]) => {
      const aIndex = CATEGORY_ORDER.indexOf(a)
      const bIndex = CATEGORY_ORDER.indexOf(b)
      if (aIndex !== -1 || bIndex !== -1) {
        return (aIndex === -1 ? Number.MAX_SAFE_INTEGER : aIndex) -
          (bIndex === -1 ? Number.MAX_SAFE_INTEGER : bIndex)
      }
      return a.localeCompare(b)
    })
    .map(([heading, categoryRows]) => ({
      category: heading,
      heading,
      rows: categoryRows,
    }))
}

function positionMenu(anchorRect: AddNodeChooserProps['anchorRect']): { left: number; top: number } {
  if (!anchorRect || typeof window === 'undefined') return { left: 16, top: 16 }

  const opensRight = anchorRect.right + MENU_GAP_PX + MENU_WIDTH_PX <= window.innerWidth - MENU_GAP_PX
  const preferredLeft = opensRight
    ? anchorRect.right + MENU_GAP_PX
    : anchorRect.left - MENU_GAP_PX - MENU_WIDTH_PX
  const left = Math.min(
    Math.max(preferredLeft, MENU_GAP_PX),
    Math.max(window.innerWidth - MENU_WIDTH_PX - MENU_GAP_PX, MENU_GAP_PX),
  )
  const opensBelow =
    anchorRect.bottom + MENU_GAP_PX + MENU_PLACEMENT_HEIGHT_PX <= window.innerHeight - MENU_GAP_PX
  const preferredTop = opensBelow
    ? anchorRect.bottom + MENU_GAP_PX
    : anchorRect.top - MENU_GAP_PX - MENU_PLACEMENT_HEIGHT_PX
  const top = Math.min(
    Math.max(preferredTop, MENU_GAP_PX),
    Math.max(window.innerHeight - MENU_PLACEMENT_HEIGHT_PX - MENU_GAP_PX, MENU_GAP_PX),
  )

  return { left, top }
}

export default function AddNodeChooser({
  open,
  onOpenChange,
  compatibility,
  onSelect,
  anchorRect,
}: AddNodeChooserProps) {
  const menuRef = useRef<HTMLDivElement>(null)

  const allRows = useMemo<FlatRow[]>(() => {
    const enabled = compatibility.enabled.map((row) => ({ ...row, rowKey: `e-${row.type}` }))
    const disabled = compatibility.disabled.map((row) => ({ ...row, rowKey: `d-${row.type}` }))
    return [...enabled, ...disabled]
  }, [compatibility])

  const grouped = useMemo(() => groupRows(allRows), [allRows])
  const [activeCategory, setActiveCategory] = useState<string | null>(null)
  const menuPosition = useMemo(() => positionMenu(anchorRect), [anchorRect])

  const activeGroup = useMemo<Group | null>(() => {
    if (grouped.length === 0) return null
    return grouped.find((group) => group.category === activeCategory) ?? grouped[0] ?? null
  }, [activeCategory, grouped])

  useEffect(() => {
    if (!open) return
    setActiveCategory((current) =>
      current && grouped.some((group) => group.category === current)
        ? current
        : (grouped[0]?.category ?? null),
    )
  }, [grouped, open])

  useEffect(() => {
    if (!open) return

    const handlePointerDown = (event: PointerEvent) => {
      if (menuRef.current?.contains(event.target as Node)) return
      onOpenChange(false)
    }
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        onOpenChange(false)
      }
    }

    document.addEventListener('pointerdown', handlePointerDown)
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('pointerdown', handlePointerDown)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [onOpenChange, open])

  const handleSelect = (type: string) => {
    onSelect(type)
    onOpenChange(false)
  }

  if (!open) return null

  return (
    <div
      ref={menuRef}
      className="fixed z-50 flex max-h-[360px] w-[340px] overflow-hidden rounded-lg border bg-neutral-900 text-neutral-50 shadow-xl"
      style={{ left: menuPosition.left, top: menuPosition.top }}
      role="dialog"
      aria-label="Add a step"
    >
      <div className="w-28 shrink-0 border-r border-white/10 p-2">
        {grouped.length === 0 ? (
          <p className="px-3 py-4 text-sm text-neutral-300">No steps are available yet.</p>
        ) : (
          grouped.map((group) => (
            <button
              key={group.category}
              type="button"
              className={cn(
                'flex w-full items-center justify-between rounded-md px-3 py-2.5 text-left text-sm transition-colors',
                activeGroup?.category === group.category
                  ? 'bg-black text-white'
                  : 'text-neutral-200 hover:bg-white/10',
              )}
              onMouseEnter={() => setActiveCategory(group.category)}
              onFocus={() => setActiveCategory(group.category)}
              onClick={() => setActiveCategory(group.category)}
            >
              <span>{group.heading}</span>
              <ChevronRight className="h-4 w-4 text-neutral-400" />
            </button>
          ))
        )}
      </div>

      <div className="max-h-[360px] min-w-0 flex-1 overflow-y-auto p-2">
        {compatibility.enabled.length === 0 && compatibility.disabled.length > 0 && (
          <p className="px-3 py-2 text-xs text-neutral-300">
            Nothing can be added here yet. Disabled steps explain what this branch needs first.
          </p>
        )}

        {activeGroup ? (
          <div className="space-y-1">
            {activeGroup.rows.map((row) => (
              <button
                key={row.rowKey}
                type="button"
                disabled={!row.enabled}
                onClick={() => row.enabled && handleSelect(row.type)}
                className={cn(
                  'w-full rounded-md px-3 py-3 text-left transition-colors',
                  row.enabled && 'text-white hover:bg-white/10',
                  !row.enabled && 'cursor-not-allowed text-neutral-500',
                )}
              >
                <span className="block text-sm font-medium leading-snug">{row.label}</span>
                <span
                  className={cn(
                    'mt-0.5 block text-xs leading-snug',
                    row.enabled ? 'text-neutral-400' : 'text-neutral-500',
                  )}
                >
                  {chooserBlurb(row)}
                </span>
                {!row.enabled && row.reason ? (
                  <span className="mt-1.5 block text-xs leading-snug text-amber-300/80">{row.reason}</span>
                ) : null}
              </button>
            ))}
          </div>
        ) : (
          <p className="px-3 py-4 text-sm text-neutral-300">No steps are available yet.</p>
        )}
      </div>
    </div>
  )
}
