import { useState, useEffect, useRef } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { listLocations, deleteLocation, LOCATION_TYPES, Location } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Loader2, Trash2 } from 'lucide-react'
import Pagination from '@/components/Pagination'
import CanonicalSourceIcon from '@/components/CanonicalSourceIcon'

export default function Locations() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [locations, setLocations] = useState<Location[]>([])
  const [loading, setLoading] = useState(true)
  const [projectSlug, setProjectSlug] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [locationTypeFilter, setLocationTypeFilter] = useState<string>('all')
  const [debouncedSearchQuery, setDebouncedSearchQuery] = useState('')
  const [currentPage, setCurrentPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [hasNext, setHasNext] = useState(false)
  const [hasPrev, setHasPrev] = useState(false)
  const [deleteDialog, setDeleteDialog] = useState<{ open: boolean; location: Location | null }>({ open: false, location: null })
  const [deleting, setDeleting] = useState(false)
  const locationsPerPage = 25
  const prevFiltersRef = useRef({ statusFilter, locationTypeFilter, debouncedSearchQuery })

  // Sync list page from URL (e.g. when returning from detail or direct link with ?page=5)
  useEffect(() => {
    const slug = searchParams.get('project') || ''
    const page = Math.max(1, parseInt(searchParams.get('page') || '1', 10))
    setProjectSlug(slug)
    setCurrentPage(page)
  }, [searchParams])

  // Debounce search query
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearchQuery(searchQuery)
    }, 300)
    return () => clearTimeout(timer)
  }, [searchQuery])

  const loadLocations = async (slug: string, q?: string, status?: string, typeFilter?: string, page: number = 1) => {
    try {
      setLoading(true)
      const offset = (page - 1) * locationsPerPage
      const data = await listLocations(slug, q, status, typeFilter, locationsPerPage, offset)
      setLocations(data.locations)
      setTotal(data.total)
      setHasNext(data.has_next)
      setHasPrev(data.has_prev)
    } catch (error) {
      console.error('Failed to load locations:', error)
    } finally {
      setLoading(false)
    }
  }

  // Reset to page 1 only when user actually changes a filter (not on mount or when URL has page=N)
  useEffect(() => {
    const prev = prevFiltersRef.current
    const changed =
      prev.statusFilter !== statusFilter ||
      prev.locationTypeFilter !== locationTypeFilter ||
      prev.debouncedSearchQuery !== debouncedSearchQuery
    prevFiltersRef.current = { statusFilter, locationTypeFilter, debouncedSearchQuery }
    if (!changed) return
    setCurrentPage(1)
    setSearchParams((prevParams) => {
      const next = new URLSearchParams(prevParams)
      next.set('page', '1')
      return next
    })
  }, [statusFilter, locationTypeFilter, debouncedSearchQuery])

  useEffect(() => {
    if (!projectSlug) return
    const status = statusFilter === 'all' ? undefined : statusFilter
    const typeFilter = locationTypeFilter === 'all' ? undefined : locationTypeFilter
    loadLocations(projectSlug, debouncedSearchQuery || undefined, status, typeFilter, currentPage)
  }, [currentPage, statusFilter, locationTypeFilter, projectSlug, debouncedSearchQuery])

  return (
    <div className="container mx-auto p-6">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-3xl font-bold">Locations</h1>
        <div className="flex gap-2">
          <Link to={`/locations/candidates?project=${projectSlug}`}>
            <Button variant="outline">Candidates</Button>
          </Link>
          <Link to={`/locations/create?project=${projectSlug}`}>
            <Button variant="outline">Create</Button>
          </Link>
          <Link to={`/import?project=${projectSlug}`}>
            <Button variant="outline">Import</Button>
          </Link>
        </div>
      </div>

      <div className="grid grid-cols-12 gap-4">
        {/* Filters sidebar */}
        <div className="col-span-3">
          <Card>
            <CardHeader>
              <CardTitle>Filters</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <Label>Search</Label>
                <Input
                  placeholder="Search names, types..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                />
              </div>

              <div>
                <Label>Status</Label>
                <Select value={statusFilter} onValueChange={setStatusFilter}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All</SelectItem>
                    <SelectItem value="active">Active</SelectItem>
                    <SelectItem value="draft">Draft</SelectItem>
                    <SelectItem value="inactive">Inactive</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div>
                <Label>Location Type</Label>
                <Select value={locationTypeFilter} onValueChange={setLocationTypeFilter}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Types</SelectItem>
                    {LOCATION_TYPES.map((type) => (
                      <SelectItem key={type} value={type}>
                        {type}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Main content */}
        <div className="col-span-9">
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          ) : locations.length === 0 ? (
            <Card>
              <CardContent className="py-8 text-center text-muted-foreground">
                No locations found
              </CardContent>
            </Card>
          ) : (
            <>
              {total > locationsPerPage && (
                <div className="mb-4">
                  <Pagination
                    page={currentPage}
                    perPage={locationsPerPage}
                    total={total}
                    totalPages={Math.ceil(total / locationsPerPage)}
                    hasNext={hasNext}
                    hasPrev={hasPrev}
                    onPageChange={(page) => {
                      setCurrentPage(page)
                      setSearchParams((prev) => {
                        const next = new URLSearchParams(prev)
                        next.set('page', String(page))
                        return next
                      })
                    }}
                    itemLabel="locations"
                  />
                </div>
              )}
              <div className="grid gap-4">
                {locations.map((location) => (
                  <Card key={location.id}>
                    <CardHeader>
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <div className="flex items-center gap-2">
                            <CanonicalSourceIcon createdByUserId={location.created_by_user_id} />
                            <CardTitle>
                              <Link to={`/locations/canonical/${location.id}?project=${projectSlug}&page=${currentPage}`} state={{ fromListPage: currentPage }} className="hover:underline">
                                {location.name}
                              </Link>
                            </CardTitle>
                          </div>
                          <CardDescription>
                            {location.location_type} • {location.status}
                            {location.mention_count !== undefined && (
                              <> • {location.mention_count} mention{location.mention_count !== 1 ? 's' : ''}</>
                            )}
                          </CardDescription>
                        </div>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setDeleteDialog({ open: true, location })}
                          className="ml-4"
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </CardHeader>
                  </Card>
                ))}
              </div>
              {total > locationsPerPage && (
                <div className="mt-4">
                  <Pagination
                    page={currentPage}
                    perPage={locationsPerPage}
                    total={total}
                    totalPages={Math.ceil(total / locationsPerPage)}
                    hasNext={hasNext}
                    hasPrev={hasPrev}
                    onPageChange={(page) => {
                      setCurrentPage(page)
                      setSearchParams((prev) => {
                        const next = new URLSearchParams(prev)
                        next.set('page', String(page))
                        return next
                      })
                    }}
                    itemLabel="locations"
                  />
                </div>
              )}
            </>
          )}
        </div>
      </div>

      <Dialog open={deleteDialog.open} onOpenChange={(open) => !deleting && setDeleteDialog(prev => ({ ...prev, open, location: open ? prev.location : null }))}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Canonical Location</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete "{deleteDialog.location?.name}"? This will unlink all mentions and return them to the candidate pool. This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteDialog({ open: false, location: null })} disabled={deleting}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={async () => {
                if (!deleteDialog.location) return
                setDeleting(true)
                try {
                  await deleteLocation(deleteDialog.location.id, projectSlug)
                  setDeleteDialog({ open: false, location: null })
                  // Reload locations
                  const status = statusFilter === 'all' ? undefined : statusFilter
                  const typeFilter = locationTypeFilter === 'all' ? undefined : locationTypeFilter
                  await loadLocations(projectSlug, debouncedSearchQuery || undefined, status, typeFilter, currentPage)
                } catch (error) {
                  console.error('Failed to delete location:', error)
                  alert('Failed to delete location')
                } finally {
                  setDeleting(false)
                }
              }}
            >
              {deleting ? 'Deleting...' : 'Delete'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
