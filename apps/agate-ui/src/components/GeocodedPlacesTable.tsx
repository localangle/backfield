import { Fragment, useCallback, useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  getGeocodedPlaceDisplay,
  getGeocodingSourceLabel,
  getPlaceEditorialDetail,
  extractGeometryFromPlace,
  placeEditorialDetailHasContent,
} from '@/lib/processedItemPlaceGeometry'
import { mentionNatureBadgeClass, mentionNatureDisplayLabel } from '@/lib/placeMentionNature'
import { placeExtractTypeLabel } from '@/lib/placeExtractTypeLabel'
import { isMergedRowLinkedToStylebook, shouldShowAdoptForStylebook } from '@/lib/processedItemReviewRow'
import { cn } from '@/lib/utils'
import { BookMarked, ChevronDown, ChevronRight, ExternalLink, Trash2 } from 'lucide-react'

function PlaceNatureBadges({
  nature,
  secondaryTags,
}: {
  nature: string
  secondaryTags: string[]
}) {
  const pills: string[] = []
  if (nature) pills.push(nature)
  for (const tag of secondaryTags) {
    if (tag && !pills.includes(tag)) pills.push(tag)
  }
  if (pills.length === 0) return null
  return (
    <div className="flex flex-wrap gap-1.5">
      {pills.map((tag) => (
        <Badge
          key={tag}
          variant="outline"
          className={cn('font-medium shadow-none text-[11px]', mentionNatureBadgeClass(tag))}
        >
          {mentionNatureDisplayLabel(tag)}
        </Badge>
      ))}
    </div>
  )
}

export interface GeocodedPlacesTableProps {
  rows: Array<Record<string, unknown>>
  selectedAnchor: string | null
  staleAnchorSet: Set<string>
  getRowAnchor: (row: Record<string, unknown>) => string
  onSelectAnchor: (anchor: string) => void
  onOpenStylebookPlace?: (row: Record<string, unknown>) => void
  onAdoptForStylebook?: (row: Record<string, unknown>) => void
  adoptDisabled?: boolean
  onDeletePlace?: (row: Record<string, unknown>) => void
  deleteDisabled?: boolean
  onFindOnMap?: (row: Record<string, unknown>) => void
}

export function GeocodedPlacesTable({
  rows,
  selectedAnchor,
  staleAnchorSet,
  getRowAnchor,
  onSelectAnchor,
  onOpenStylebookPlace,
  onAdoptForStylebook,
  adoptDisabled = false,
  onDeletePlace,
  deleteDisabled = false,
  onFindOnMap,
}: GeocodedPlacesTableProps) {
  const [expandedAnchors, setExpandedAnchors] = useState<Set<string>>(() => new Set())

  const toggleExpanded = useCallback((anchor: string) => {
    setExpandedAnchors((prev) => {
      const next = new Set(prev)
      if (next.has(anchor)) next.delete(anchor)
      else next.add(anchor)
      return next
    })
  }, [])

  if (rows.length === 0) {
    return <p className="text-xs text-muted-foreground">No geocoded places are listed for this item yet.</p>
  }

  return (
    <div className="min-h-0 min-w-0 flex-1 overflow-y-auto rounded-md border">
      <Table className="w-full table-fixed">
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead className="h-7 w-7 px-1 py-0" aria-label="Expand row" />
            <TableHead className="h-7 w-[38%] px-2 py-0 text-[11px] font-medium">Name</TableHead>
            <TableHead className="h-7 w-[14%] px-2 py-0 text-[11px] font-medium">Type</TableHead>
            <TableHead className="h-7 px-2 py-0 text-[11px] font-medium">Address</TableHead>
            <TableHead className="h-7 w-[9rem] px-1 py-0 text-right text-[11px] font-medium">
              <span className="sr-only">Actions</span>
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row, idx) => {
            const anchor = getRowAnchor(row)
            const loc = row.location as Record<string, unknown> | undefined
            const display = getGeocodedPlaceDisplay(loc)
            const editorial = getPlaceEditorialDetail(loc)
            const canExpand = placeEditorialDetailHasContent(editorial)
            const expanded = Boolean(anchor && expandedAnchors.has(anchor))
            const selected = selectedAnchor === anchor
            const rowStale = row.stale === true || (anchor ? staleAnchorSet.has(anchor) : false)
            const name = display.name || '—'
            const address = display.formattedAddress || '—'
            const linked = isMergedRowLinkedToStylebook(row)
            const showAdopt = shouldShowAdoptForStylebook(row)
            const geocodingSourceLabel = loc ? getGeocodingSourceLabel(loc) : null
            const needsGeography = !extractGeometryFromPlace(loc)
            const typeLabel = display.type.trim()
              ? placeExtractTypeLabel(display.type)
              : '—'

            return (
              <Fragment key={anchor || `geo-${idx}`}>
                <TableRow
                  id={anchor ? `geo-place-row-${anchor}` : undefined}
                  tabIndex={0}
                  data-state={selected ? 'selected' : undefined}
                  className={cn(
                    'cursor-pointer text-xs',
                    selected && 'bg-primary/10 hover:bg-primary/10',
                    rowStale && 'border-l-2 border-l-amber-400',
                  )}
                  onClick={() => {
                    if (anchor) onSelectAnchor(anchor)
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      if (anchor) onSelectAnchor(anchor)
                    }
                  }}
                >
                  <TableCell className="w-7 px-1 py-1.5 align-middle">
                    {canExpand && anchor ? (
                      <button
                        type="button"
                        className="inline-flex h-6 w-6 items-center justify-center rounded-sm text-muted-foreground hover:bg-muted hover:text-foreground"
                        aria-expanded={expanded}
                        aria-label={expanded ? 'Collapse details' : 'Expand details'}
                        onClick={(e) => {
                          e.stopPropagation()
                          toggleExpanded(anchor)
                        }}
                      >
                        {expanded ? (
                          <ChevronDown className="h-3.5 w-3.5" aria-hidden />
                        ) : (
                          <ChevronRight className="h-3.5 w-3.5" aria-hidden />
                        )}
                      </button>
                    ) : (
                      <span className="inline-block h-6 w-6" aria-hidden />
                    )}
                  </TableCell>
                  <TableCell className="min-w-0 px-2 py-1.5 align-middle font-medium" title={name}>
                    <div className="flex min-w-0 flex-col gap-1">
                      <span className="truncate leading-snug">{name}</span>
                      {geocodingSourceLabel ? (
                        <Badge
                          variant="outline"
                          className="w-fit max-w-full truncate text-[10px] font-normal text-muted-foreground"
                          title={geocodingSourceLabel}
                        >
                          {geocodingSourceLabel}
                        </Badge>
                      ) : null}
                      {needsGeography ? (
                        <Badge
                          variant="outline"
                          className="w-fit max-w-full truncate border-amber-300 bg-amber-50 text-[10px] font-normal text-amber-900 dark:border-amber-800 dark:bg-amber-950/30 dark:text-amber-100"
                        >
                          Needs geography
                        </Badge>
                      ) : null}
                    </div>
                  </TableCell>
                  <TableCell
                    className="truncate px-2 py-1.5 align-middle text-muted-foreground"
                    title={typeLabel}
                  >
                    {typeLabel}
                  </TableCell>
                  <TableCell
                    className="min-w-0 truncate px-2 py-1.5 align-middle text-muted-foreground"
                    title={address}
                  >
                    {address}
                  </TableCell>
                  <TableCell
                    className="w-[9rem] px-1 py-1.5 align-middle"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <div className="flex items-center justify-end gap-0.5">
                      {needsGeography && onFindOnMap ? (
                        <Button
                          type="button"
                          variant="secondary"
                          size="sm"
                          className="h-7 shrink-0 px-2 text-[11px]"
                          onClick={() => onFindOnMap(row)}
                        >
                          Find on map
                        </Button>
                      ) : null}
                      {linked && onOpenStylebookPlace ? (
                        <Button
                          type="button"
                          variant="outline"
                          size="icon"
                          className="h-7 w-7 shrink-0"
                          aria-label="Open in Stylebook"
                          title="Open in Stylebook"
                          onClick={() => onOpenStylebookPlace(row)}
                        >
                          <ExternalLink className="h-3.5 w-3.5" aria-hidden />
                        </Button>
                      ) : null}
                      {showAdopt && onAdoptForStylebook ? (
                        <Button
                          type="button"
                          variant="secondary"
                          size="icon"
                          className="h-7 w-7 shrink-0"
                          aria-label="Adopt for Stylebook"
                          title="Adopt for Stylebook"
                          disabled={adoptDisabled}
                          onClick={() => onAdoptForStylebook(row)}
                        >
                          <BookMarked className="h-3.5 w-3.5" aria-hidden />
                        </Button>
                      ) : null}
                      {onDeletePlace ? (
                        <Button
                          type="button"
                          variant="outline"
                          size="icon"
                          className="h-7 w-7 shrink-0 text-destructive hover:text-destructive"
                          aria-label="Remove place from story"
                          title="Remove from story"
                          disabled={deleteDisabled}
                          onClick={() => onDeletePlace(row)}
                        >
                          <Trash2 className="h-3.5 w-3.5" aria-hidden />
                        </Button>
                      ) : null}
                      {!linked && !showAdopt && !onDeletePlace ? (
                        <span className="px-1 text-[10px] text-muted-foreground" aria-hidden>
                          —
                        </span>
                      ) : null}
                    </div>
                  </TableCell>
                </TableRow>
                {expanded && canExpand ? (
                  <TableRow className="hover:bg-transparent">
                    <TableCell colSpan={5} className="bg-muted/25 px-3 py-2">
                      <div className="flex flex-col gap-2">
                        <PlaceNatureBadges
                          nature={editorial.nature}
                          secondaryTags={editorial.natureSecondaryTags}
                        />
                        {editorial.roleInStory ? (
                          <p className="text-xs leading-relaxed text-muted-foreground">
                            {editorial.roleInStory}
                          </p>
                        ) : null}
                      </div>
                    </TableCell>
                  </TableRow>
                ) : null}
              </Fragment>
            )
          })}
        </TableBody>
      </Table>
    </div>
  )
}
