import { useState, useEffect, useMemo, useRef } from 'react'
import { EntityConfig } from '@/lib/entityTypes'
import { stringSimilarity } from '@/lib/utils'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { ArrowUpDown, ArrowUp, ArrowDown, Sparkles } from 'lucide-react'

type SortField = string | null
type SortDirection = 'asc' | 'desc'

interface EntitySelectorProps<T> {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSelect: (entityId: number, displayName?: string) => void
  projectSlug: string
  candidateNames?: string[]
  /** IDs to exclude from the list (e.g. current entity when reassigning) */
  excludeIds?: number[]
  config: EntityConfig<T>
}

export default function EntitySelector<T extends { id: number }>({
  open,
  onOpenChange,
  onSelect,
  projectSlug,
  candidateNames = [],
  excludeIds = [],
  config,
}: EntitySelectorProps<T>) {
  const [entities, setEntities] = useState<T[]>([])
  const [loading, setLoading] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [sortField, setSortField] = useState<SortField>(null)
  const [sortDirection, setSortDirection] = useState<SortDirection>('asc')
  const searchTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const didLoadOnOpenRef = useRef(false)

  // Get sortable fields from config
  const sortableFields = useMemo(() => {
    return config.fields.filter(f => f.sortable).map(f => f.key)
  }, [config])

  // Exclude specific entities (e.g. current entity when reassigning)
  const filteredEntities = useMemo(() => {
    if (!excludeIds.length) return entities
    const exclude = new Set(excludeIds)
    return entities.filter(e => !exclude.has(e.id))
  }, [entities, excludeIds])

  useEffect(() => {
    if (open) {
      // When we have candidate names, use the first as initial search so API returns relevant matches
      // (e.g. "Kansas" fetches Kansas/Arkansas; without this we'd get first 100 alphabetically)
      const initialQuery = candidateNames.length > 0 ? candidateNames[0] : ''
      setSearchQuery(initialQuery)
      didLoadOnOpenRef.current = true
      loadEntities(initialQuery)
    }
  }, [open, projectSlug])

  // Debounced search effect (only when user types; skip duplicate load when we just opened with empty query)
  useEffect(() => {
    if (!open) return

    if (searchTimeoutRef.current) {
      clearTimeout(searchTimeoutRef.current)
    }

    const isInitialOpenWithEmptyQuery = didLoadOnOpenRef.current && searchQuery === ''
    if (isInitialOpenWithEmptyQuery) {
      didLoadOnOpenRef.current = false
      return
    }

    searchTimeoutRef.current = setTimeout(() => {
      loadEntities(searchQuery)
    }, 300)

    return () => {
      if (searchTimeoutRef.current) {
        clearTimeout(searchTimeoutRef.current)
      }
    }
  }, [searchQuery, open])
  
  // Calculate suggested entities based on candidate names
  const suggestedEntities = useMemo(() => {
    if (candidateNames.length === 0 || filteredEntities.length === 0) return []
    
    const suggestions: Array<{ entity: T; score: number }> = []
    
    for (const entity of filteredEntities) {
      // Only include active entities in suggestions
      if ('status' in entity && entity.status !== 'active') {
        continue
      }
      
      let maxScore = 0
      const entityName = config.getCanonicalName(entity)
      for (const candidateName of candidateNames) {
        const score = stringSimilarity(candidateName, entityName)
        maxScore = Math.max(maxScore, score)
      }
      
      if (maxScore >= 60) {
        suggestions.push({ entity, score: maxScore })
      }
    }
    
    suggestions.sort((a, b) => b.score - a.score)
    return suggestions.slice(0, 5).map(s => s.entity)
  }, [candidateNames, filteredEntities, config])

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc')
    } else {
      setSortField(field)
      setSortDirection('asc')
    }
  }

  const sortedAndFilteredEntities = useMemo(() => {
    let result = filteredEntities

    if (sortField) {
      result = [...result].sort((a, b) => {
        const fields = config.getCanonicalDisplayFields(a)
        const fieldsB = config.getCanonicalDisplayFields(b)
        const aValue = fields[sortField] || ''
        const bValue = fieldsB[sortField] || ''

        const comparison = String(aValue).localeCompare(String(bValue))
        return sortDirection === 'asc' ? comparison : -comparison
      })
    }

    // When user is searching, show all results in the main list (Suggested is hidden).
    // When search is empty, dedupe so suggested matches appear only in the Suggested section.
    if (!searchQuery.trim()) {
      const suggestedIds = new Set(suggestedEntities.map(e => e.id))
      result = result.filter(entity => !suggestedIds.has(entity.id))
    }

    return result
  }, [filteredEntities, searchQuery, sortField, sortDirection, suggestedEntities, config])

  const loadEntities = async (query?: string) => {
    try {
      setLoading(true)
      const searchQuery = query?.trim() || undefined
      const listFn = config.api.listCanonicalForSelector ?? config.api.listCanonical
      const limit = config.api.listCanonicalForSelector ? 100 : (searchQuery ? 200 : 500)
      const data = (await listFn(projectSlug, searchQuery, "active", limit, 0)) as Record<string, unknown>

      if ("locations" in data && Array.isArray(data.locations)) {
        setEntities(data.locations as T[])
      } else if ("people" in data && Array.isArray(data.people)) {
        setEntities(data.people as T[])
      } else if ("organizations" in data && Array.isArray(data.organizations)) {
        setEntities(data.organizations as T[])
      } else if (Array.isArray(data)) {
        setEntities(data as T[])
      } else {
        setEntities([])
      }
    } catch (error) {
      console.error('Failed to load entities:', error)
      setEntities([])
    } finally {
      setLoading(false)
    }
  }

  const handleSelect = (entity: T) => {
    const displayName = config.getCanonicalName(entity)
    onSelect(entity.id, displayName)
    onOpenChange(false)
    setSearchQuery('')
    setSortField(null)
  }

  const SortIcon = ({ field }: { field: SortField }) => {
    if (sortField !== field) {
      return <ArrowUpDown className="h-4 w-4 ml-1 opacity-50" />
    }
    return sortDirection === 'asc' ? (
      <ArrowUp className="h-4 w-4 ml-1" />
    ) : (
      <ArrowDown className="h-4 w-4 ml-1" />
    )
  }

  // Get display fields for table headers
  const displayFields = config.fields.filter(f => f.key !== 'created_at' || sortableFields.includes('created_at'))

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[75vh] flex flex-col">
        <DialogHeader className="flex-shrink-0 pb-4">
          <DialogTitle>Select Canonical {config.displayName.singular}</DialogTitle>
          <DialogDescription>
            Choose an existing canonical {config.displayName.singular.toLowerCase()} to link the candidate(s) to.
          </DialogDescription>
        </DialogHeader>
        
        <div className="flex gap-2 mb-4 flex-shrink-0">
          <Input
            placeholder={`Search ${config.displayName.plural.toLowerCase()}...`}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            autoFocus
            className="flex-1"
          />
        </div>

        <div className="flex-1 overflow-y-auto border rounded-md min-h-[280px]">
          {/* Suggested entities - section stays in place when search empty; show message when none */}
          {!searchQuery.trim() && (
            <div className="border-b">
              <div className="px-4 py-2 bg-muted/30 flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-primary" />
                <span className="text-sm font-medium">Suggested Matches</span>
              </div>
              {loading && suggestedEntities.length === 0 && sortedAndFilteredEntities.length === 0 ? (
                <div className="text-center py-6 text-muted-foreground">Loading {config.displayName.plural.toLowerCase()}…</div>
              ) : suggestedEntities.length > 0 ? (
                <Table>
                    <TableHeader>
                      <TableRow>
                        {displayFields.map(field => (
                          <TableHead key={field.key}>{field.label}</TableHead>
                        ))}
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {suggestedEntities.map((entity) => {
                        const fields = config.getCanonicalDisplayFields(entity)
                        return (
                          <TableRow
                            key={entity.id}
                            className="cursor-pointer hover:bg-primary/10 bg-primary/5"
                            onClick={() => handleSelect(entity)}
                          >
                            {displayFields.map(field => (
                              <TableCell key={field.key} className="py-2">
                                {field.key === displayFields[0].key ? (
                                  <span className="font-medium">{fields[field.key] || '-'}</span>
                                ) : (
                                  <span className="text-muted-foreground">{fields[field.key] || '-'}</span>
                                )}
                              </TableCell>
                            ))}
                          </TableRow>
                        )
                      })}
                    </TableBody>
                </Table>
              ) : (
                <div className="text-center py-4 text-muted-foreground text-sm">No suggested {config.displayName.plural.toLowerCase()}.</div>
              )}
            </div>
          )}

          {/* All entities - section stays in place; show message when none */}
          {searchQuery.trim() && loading ? (
            <div className="text-center py-6 text-muted-foreground">Loading {config.displayName.plural.toLowerCase()}…</div>
          ) : sortedAndFilteredEntities.length === 0 ? (
                <div className="text-center py-8 text-muted-foreground">
                  {searchQuery ? `No ${config.displayName.plural.toLowerCase()} found matching your search` : `No ${config.displayName.plural.toLowerCase()} available`}
                </div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      {displayFields.map(field => (
                        <TableHead 
                          key={field.key}
                          className={sortableFields.includes(field.key) ? "cursor-pointer hover:bg-muted/50 select-none" : ""}
                          onClick={() => sortableFields.includes(field.key) && handleSort(field.key)}
                        >
                          <div className="flex items-center">
                            {field.label}
                            {sortableFields.includes(field.key) && <SortIcon field={field.key} />}
                          </div>
                        </TableHead>
                      ))}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {sortedAndFilteredEntities.map((entity) => {
                      const fields = config.getCanonicalDisplayFields(entity)
                      return (
                        <TableRow
                          key={entity.id}
                          className="cursor-pointer hover:bg-muted/50"
                          onClick={() => handleSelect(entity)}
                        >
                          {displayFields.map(field => (
                            <TableCell key={field.key} className="py-2">
                              {field.key === displayFields[0].key ? (
                                <span className="font-medium">{fields[field.key] || '-'}</span>
                              ) : (
                                <span className="text-muted-foreground">{fields[field.key] || '-'}</span>
                              )}
                            </TableCell>
                          ))}
                        </TableRow>
                      )
                    })}
                  </TableBody>
                </Table>
              )}
        </div>

        <DialogFooter className="flex-shrink-0">
          <div className="text-sm text-muted-foreground mr-auto">
            {suggestedEntities.length + sortedAndFilteredEntities.length} {config.displayName.singular.toLowerCase()}
            {(suggestedEntities.length + sortedAndFilteredEntities.length) !== 1 ? 's' : ''}
            {suggestedEntities.length > 0 && !searchQuery.trim() && (
              <span className="ml-2">({suggestedEntities.length} suggested)</span>
            )}
          </div>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
