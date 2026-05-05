import { useState, useEffect, useRef, useMemo } from "react"
import { Link, useSearchParams } from "react-router-dom"
import { useAppMessage } from "@/components/AppMessageProvider"
import { useProjectCatalogScope } from "@/lib/catalogNavigation"
import { useScopeBreadcrumbRoot } from "@/lib/breadcrumbs"
import {
  deleteCanonicalLocation,
  listCanonicalLocations,
  listCanonicalLocationTypes,
  type CanonicalLocation,
} from "@/lib/api"
import { placeExtractTypeLabel, sortReviewQueueTypeFilterOptions } from "@/lib/place-extract-type-label"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Loader2, Trash2 } from "lucide-react"
import Pagination from "@/components/Pagination"
import CanonicalSourceIcon from "@/components/CanonicalSourceIcon"
import { Breadcrumbs } from "@/components/Breadcrumbs"
import { useCanEditStylebook } from "@/lib/stylebookEditContext"

export default function Locations() {
  const { showError } = useAppMessage()
  const {
    projectFilterSlug,
    filterScopeSuffix,
    filterScopeQueryString,
    stylebookSlug,
  } = useProjectCatalogScope()
  const crumbRoot = useScopeBreadcrumbRoot()
  const [searchParams, setSearchParams] = useSearchParams()
  const [canonicals, setCanonicals] = useState<CanonicalLocation[]>([])
  const [loading, setLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState("")
  const [debouncedSearchQuery, setDebouncedSearchQuery] = useState("")
  const [typeFilter, setTypeFilter] = useState<string>("all")
  const [types, setTypes] = useState<string[]>([])
  const [currentPage, setCurrentPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [hasNext, setHasNext] = useState(false)
  const [hasPrev, setHasPrev] = useState(false)
  const [deleteDialog, setDeleteDialog] = useState<{ open: boolean; row: CanonicalLocation | null }>({
    open: false,
    row: null,
  })
  const [deleting, setDeleting] = useState(false)
  const canEdit = useCanEditStylebook()
  const locationsPerPage = 25
  const prevSearchRef = useRef(debouncedSearchQuery)
  const prevTypeFilterRef = useRef(typeFilter)

  const orderedTypeFilterOptions = useMemo(
    () => sortReviewQueueTypeFilterOptions(types),
    [types],
  )

  const typeFilterParam = typeFilter === "all" ? undefined : typeFilter

  useEffect(() => {
    const page = Math.max(1, parseInt(searchParams.get("page") || "1", 10))
    setCurrentPage(page)
  }, [searchParams])

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearchQuery(searchQuery)
    }, 300)
    return () => clearTimeout(timer)
  }, [searchQuery])

  useEffect(() => {
    if (!stylebookSlug) return
    void (async () => {
      try {
        const res = await listCanonicalLocationTypes(stylebookSlug)
        setTypes(res.types)
      } catch {
        setTypes([])
      }
    })()
  }, [stylebookSlug])

  useEffect(() => {
    const prev = prevSearchRef.current
    prevSearchRef.current = debouncedSearchQuery
    if (prev !== debouncedSearchQuery) {
      setCurrentPage(1)
      setSearchParams((prevParams) => {
        const next = new URLSearchParams(prevParams)
        next.set("page", "1")
        return next
      })
    }
  }, [debouncedSearchQuery, setSearchParams])

  useEffect(() => {
    const prev = prevTypeFilterRef.current
    prevTypeFilterRef.current = typeFilter
    if (prev !== typeFilter) {
      setCurrentPage(1)
      setSearchParams((prevParams) => {
        const next = new URLSearchParams(prevParams)
        next.set("page", "1")
        return next
      })
    }
  }, [typeFilter, setSearchParams])

  const loadCanonicals = async (
    slug: string,
    q?: string,
    page: number = 1,
    tf?: string,
  ) => {
    try {
      setLoading(true)
      const offset = (page - 1) * locationsPerPage
      const data = await listCanonicalLocations(
        slug,
        q,
        locationsPerPage,
        offset,
        tf,
        projectFilterSlug || undefined,
      )
      setCanonicals(data.canonicals)
      setTotal(data.total)
      setHasNext(data.has_next)
      setHasPrev(data.has_prev)
    } catch (error) {
      console.error("Failed to load canonical locations:", error)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!stylebookSlug) return
    void loadCanonicals(
      stylebookSlug,
      debouncedSearchQuery || undefined,
      currentPage,
      typeFilterParam,
    )
  }, [currentPage, stylebookSlug, debouncedSearchQuery, typeFilterParam, projectFilterSlug])

  return (
    <div className="container mx-auto p-6">
      <div className="flex justify-between items-center mb-6">
        <div className="min-w-0">
          <Breadcrumbs
            className="mb-3"
            items={[
              { label: crumbRoot.label, to: crumbRoot.to },
              { label: "Locations" },
            ]}
          />
          <h1 className="text-3xl font-bold">Canonical locations</h1>
        </div>
        <div className="flex gap-2">
          <Link to={`/locations/candidates${filterScopeSuffix}`}>
            <Button variant="outline">Candidates</Button>
          </Link>
          <Link to={`/locations/create${filterScopeSuffix}`}>
            <Button variant="outline">Create</Button>
          </Link>
          <Link to={`/import/locations${filterScopeSuffix}`}>
            <Button variant="outline">Import</Button>
          </Link>
        </div>
      </div>

      <div className="grid grid-cols-12 gap-4">
        <div className="col-span-3">
          <Card>
            <CardHeader>
              <CardTitle>Filters</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <Label>Search</Label>
                <Input
                  placeholder="Search canonical labels…"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                />
              </div>
              <div>
                <Label>Type</Label>
                <Select value={typeFilter} onValueChange={setTypeFilter}>
                  <SelectTrigger>
                    <SelectValue placeholder="All types" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All</SelectItem>
                    {orderedTypeFilterOptions.map((t) => (
                      <SelectItem key={t} value={t}>
                        {placeExtractTypeLabel(t)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </CardContent>
          </Card>
        </div>

        <div className="col-span-9">
          {loading ? (
            <div className="flex justify-center py-8">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          ) : canonicals.length === 0 ? (
            <Card>
              <CardContent className="py-8 text-center text-muted-foreground">
                No canonical locations in this Stylebook yet
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
                        next.set("page", String(page))
                        return next
                      })
                    }}
                    itemLabel="canonicals"
                  />
                </div>
              )}
              <div className="grid gap-4">
                {canonicals.map((c) => (
                  <Card key={c.id}>
                    <CardHeader>
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <div className="flex items-center gap-2">
                            <CanonicalSourceIcon createdByUserId={undefined} />
                            <CardTitle>
                              <Link
                                to={`/locations/canonical/${c.id}?${(() => {
                                  const q = new URLSearchParams(filterScopeQueryString)
                                  q.set("page", String(currentPage))
                                  return q.toString()
                                })()}`}
                                state={{ fromListPage: currentPage }}
                                className="hover:underline"
                              >
                                {c.label}
                              </Link>
                            </CardTitle>
                          </div>
                          <CardDescription>
                            {c.location_type
                              ? placeExtractTypeLabel(c.location_type)
                              : "—"}{" "}
                            • {c.status} • {c.linked_substrate_count} linked place
                            {c.linked_substrate_count !== 1 ? "s" : ""}
                            {c.mention_count !== undefined && (
                              <>
                                {" "}
                                • {c.mention_count} mention{c.mention_count !== 1 ? "s" : ""}
                              </>
                            )}
                          </CardDescription>
                        </div>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setDeleteDialog({ open: true, row: c })}
                          className="ml-4"
                          disabled={!canEdit}
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
                        next.set("page", String(page))
                        return next
                      })
                    }}
                    itemLabel="canonicals"
                  />
                </div>
              )}
            </>
          )}
        </div>
      </div>

      <Dialog
        open={deleteDialog.open}
        onOpenChange={(open) =>
          !deleting && setDeleteDialog((prev) => ({ ...prev, open, row: open ? prev.row : null }))
        }
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete canonical location</DialogTitle>
            <DialogDescription>
              Delete &quot;{deleteDialog.row?.label}&quot;? Linked places return to the candidate
              queue. This cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setDeleteDialog({ open: false, row: null })}
              disabled={deleting}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={async () => {
                if (!deleteDialog.row) return
                if (!stylebookSlug) return
                setDeleting(true)
                try {
                  await deleteCanonicalLocation(deleteDialog.row.id, stylebookSlug)
                  setDeleteDialog({ open: false, row: null })
                  await loadCanonicals(
                    stylebookSlug,
                    debouncedSearchQuery || undefined,
                    currentPage,
                    typeFilterParam,
                  )
                } catch (error) {
                  console.error("Failed to delete canonical:", error)
                  showError("Failed to delete canonical location")
                } finally {
                  setDeleting(false)
                }
              }}
              disabled={deleting}
            >
              {deleting ? "Deleting…" : "Delete"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
