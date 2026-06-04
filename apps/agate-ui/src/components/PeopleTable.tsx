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
import { personNatureBadgeClass, personNatureDisplayLabel } from '@/lib/personMentionNature'
import {
  getMergedRowAnchor,
  personDisplayName,
  readPersonFromRow,
} from '@/lib/review/entities/person/reviewRow'
import { cn } from '@/lib/utils'
import { ChevronDown, ChevronRight, ExternalLink, Trash2 } from 'lucide-react'

function PersonNatureBadges({ nature }: { nature: string }) {
  if (!nature.trim()) return null
  return (
    <div className="flex flex-wrap gap-1.5">
      <Badge
        variant="outline"
        className={cn('w-fit font-medium shadow-none text-[11px]', personNatureBadgeClass(nature))}
      >
        {personNatureDisplayLabel(nature)}
      </Badge>
    </div>
  )
}

export interface PeopleTableProps {
  rows: Array<Record<string, unknown>>
  selectedAnchor: string | null
  onSelectAnchor: (anchor: string) => void
  onOpenStylebook?: (row: Record<string, unknown>) => void
  onDeletePerson?: (row: Record<string, unknown>) => void
  deleteDisabled?: boolean
}

export function PeopleTable({
  rows,
  selectedAnchor,
  onSelectAnchor,
  onOpenStylebook,
  onDeletePerson,
  deleteDisabled = false,
}: PeopleTableProps) {
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
    return (
      <p className="text-xs text-muted-foreground">No people were extracted for this story.</p>
    )
  }

  return (
    <div className="min-h-0 min-w-0 flex-1 overflow-y-auto rounded-md border">
      <Table className="w-full table-fixed">
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead className="h-7 w-7 px-1 py-0" aria-label="Expand row" />
            <TableHead className="h-7 w-[32%] px-2 py-0 text-[11px] font-medium">Name</TableHead>
            <TableHead className="h-7 w-[22%] px-2 py-0 text-[11px] font-medium">Title</TableHead>
            <TableHead className="h-7 px-2 py-0 text-[11px] font-medium">Affiliation</TableHead>
            <TableHead className="h-7 w-[5rem] px-1 py-0 text-right text-[11px] font-medium">
              <span className="sr-only">Actions</span>
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row, idx) => {
            const anchor = getMergedRowAnchor(row)
            const person = readPersonFromRow(row)
            const name = personDisplayName(row)
            const title = typeof person.title === 'string' ? person.title.trim() : ''
            const affiliation = typeof person.affiliation === 'string' ? person.affiliation.trim() : ''
            const nature = typeof person.nature === 'string' ? person.nature : ''
            const role = typeof person.role_in_story === 'string' ? person.role_in_story.trim() : ''
            const canExpand = Boolean(nature.trim() || role)
            const expanded = Boolean(anchor && expandedAnchors.has(anchor))
            const selected = selectedAnchor === anchor
            const titleLabel = title || '—'
            const affiliationLabel = affiliation || '—'

            return (
              <Fragment key={anchor || `person-${idx}`}>
                <TableRow
                  id={anchor ? `people-row-${anchor}` : undefined}
                  tabIndex={0}
                  data-state={selected ? 'selected' : undefined}
                  className={cn(
                    'cursor-pointer text-xs',
                    selected && 'bg-primary/10 hover:bg-primary/10',
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
                  <TableCell
                    className="min-w-0 px-2 py-1.5 align-middle font-medium"
                    title={name}
                  >
                    <span className="block truncate leading-snug">{name}</span>
                  </TableCell>
                  <TableCell
                    className="truncate px-2 py-1.5 align-middle text-muted-foreground"
                    title={titleLabel}
                  >
                    {titleLabel}
                  </TableCell>
                  <TableCell
                    className="min-w-0 truncate px-2 py-1.5 align-middle text-muted-foreground"
                    title={affiliationLabel}
                  >
                    {affiliationLabel}
                  </TableCell>
                  <TableCell
                    className="w-[5rem] px-1 py-1.5 align-middle"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <div className="flex items-center justify-end gap-0.5">
                      {onOpenStylebook ? (
                        <Button
                          type="button"
                          variant="outline"
                          size="icon"
                          className="h-7 w-7 shrink-0"
                          aria-label="Open in Stylebook"
                          title="Open in Stylebook"
                          onClick={() => onOpenStylebook(row)}
                        >
                          <ExternalLink className="h-3.5 w-3.5" aria-hidden />
                        </Button>
                      ) : null}
                      {onDeletePerson ? (
                        <Button
                          type="button"
                          variant="outline"
                          size="icon"
                          className="h-7 w-7 shrink-0 text-destructive hover:text-destructive"
                          aria-label="Remove person from story"
                          title="Remove from story"
                          disabled={deleteDisabled}
                          onClick={() => onDeletePerson(row)}
                        >
                          <Trash2 className="h-3.5 w-3.5" aria-hidden />
                        </Button>
                      ) : null}
                      {!onOpenStylebook && !onDeletePerson ? (
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
                        <PersonNatureBadges nature={nature} />
                        {role ? (
                          <p className="text-xs leading-relaxed text-muted-foreground">{role}</p>
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
