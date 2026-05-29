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
  getMergedRowCanonicalLinkStatus,
  getMergedRowStylebookLink,
  isMergedRowLinkedToStylebook,
  personDisplayName,
  readPersonFromRow,
} from '@/lib/review/entities/person/reviewRow'
import { cn } from '@/lib/utils'
import { ChevronDown, ChevronRight, ExternalLink, Trash2 } from 'lucide-react'

function PersonNatureBadges({ nature }: { nature: string }) {
  if (!nature.trim()) return null
  return (
    <Badge
      variant="outline"
      className={cn('font-medium shadow-none text-[11px]', personNatureBadgeClass(nature))}
    >
      {personNatureDisplayLabel(nature)}
    </Badge>
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
      <p className="py-8 text-center text-sm text-muted-foreground">
        No people were extracted for this story.
      </p>
    )
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-8" />
          <TableHead>Name</TableHead>
          <TableHead>Title</TableHead>
          <TableHead>Affiliation</TableHead>
          <TableHead>Link</TableHead>
          <TableHead className="w-[88px]">Actions</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((row) => {
          const anchor = getMergedRowAnchor(row)
          const person = readPersonFromRow(row)
          const name = personDisplayName(row)
          const title = typeof person.title === 'string' ? person.title : ''
          const affiliation = typeof person.affiliation === 'string' ? person.affiliation : ''
          const nature = typeof person.nature === 'string' ? person.nature : ''
          const role = typeof person.role_in_story === 'string' ? person.role_in_story : ''
          const linked = isMergedRowLinkedToStylebook(row)
          const linkStatus = getMergedRowCanonicalLinkStatus(row)
          const linkLabel = getMergedRowStylebookLink(row)?.label
          const expanded = expandedAnchors.has(anchor)
          const selected = selectedAnchor === anchor
          return (
            <Fragment key={anchor}>
              <TableRow
                id={`people-row-${anchor}`}
                className={cn('cursor-pointer', selected && 'bg-primary/10')}
                onClick={() => onSelectAnchor(anchor)}
              >
                <TableCell className="p-2">
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7"
                    onClick={(e) => {
                      e.stopPropagation()
                      toggleExpanded(anchor)
                    }}
                  >
                    {expanded ? (
                      <ChevronDown className="h-4 w-4" />
                    ) : (
                      <ChevronRight className="h-4 w-4" />
                    )}
                  </Button>
                </TableCell>
                <TableCell className="font-medium">{name}</TableCell>
                <TableCell className="text-muted-foreground">{title || '—'}</TableCell>
                <TableCell className="text-muted-foreground">{affiliation || '—'}</TableCell>
                <TableCell>
                  {linked ? (
                    <span className="text-xs text-green-700">{linkLabel ?? 'Linked'}</span>
                  ) : (
                    <span className="text-xs text-muted-foreground">
                      {linkStatus === 'pending' ? 'Needs review' : 'Unlinked'}
                    </span>
                  )}
                </TableCell>
                <TableCell>
                  <div className="flex items-center gap-1">
                    {onOpenStylebook ? (
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8"
                        title="Open in Stylebook"
                        onClick={(e) => {
                          e.stopPropagation()
                          onOpenStylebook(row)
                        }}
                      >
                        <ExternalLink className="h-4 w-4" />
                      </Button>
                    ) : null}
                    {onDeletePerson ? (
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 text-destructive"
                        disabled={deleteDisabled}
                        title="Remove from story"
                        onClick={(e) => {
                          e.stopPropagation()
                          onDeletePerson(row)
                        }}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    ) : null}
                  </div>
                </TableCell>
              </TableRow>
              {expanded ? (
                <TableRow className="bg-muted/30 hover:bg-muted/30">
                  <TableCell colSpan={6} className="py-3">
                    <div className="flex flex-wrap items-center gap-2 text-sm">
                      <PersonNatureBadges nature={nature} />
                      {role ? (
                        <span className="text-muted-foreground">{role}</span>
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
  )
}
