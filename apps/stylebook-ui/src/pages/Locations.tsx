import { useState, useEffect, useMemo, useCallback } from "react"
import { Link, useSearchParams } from "react-router-dom"
import { useAppMessage } from "@/components/AppMessageProvider"
import { useProjectCatalogScope } from "@/lib/catalogNavigation"
import { useScopeBreadcrumbRoot } from "@/lib/breadcrumbs"
import {
  deleteCanonicalLocation,
  fetchProjects,
  listCanonicalLocations,
  listCanonicalLocationTypes,
  type CanonicalListSort,
  type CanonicalLocation,
  type Project,
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
import { Breadcrumbs } from "@/components/Breadcrumbs"
import { useCanEditStylebook } from "@/lib/stylebookEditContext"

/** Query keys for the canonical list; preserved when opening detail and on breadcrumb/back. */
function parseCanonicalListSearchParams(sp: URLSearchParams) {
  const qRaw = sp.get("q") ?? ""
  const q = qRaw.trim()
  const typeRaw = sp.get("type") ?? ""
  const typeFilter = typeRaw && typeRaw !== "all" ? typeRaw : "all"
  const typeFilterParam = typeFilter === "all" ? undefined : typeFilter
  const sortBy: CanonicalListSort = sp.get("sort") === "recent" ? "recent" : "label"
  const minMentions = Math.max(0, parseInt(sp.get("min_mentions") ?? "0", 10) || 0)
  const page = Math.max(1, parseInt(sp.get("page") ?? "1", 10) || 1)
  return { q, typeFilter, typeFilterParam, sortBy, minMentions, page }
}

export default function Locations() {
  const { showError } = useAppMessage()
  const {
    projectScopeSlug,
    projectFilterSlug,
    filterScopeSuffix,
    stylebookSlug,
    catalogBasePath,
  } = useProjectCatalogScope()
  const crumbRoot = useScopeBreadcrumbRoot()
  const [searchParams, setSearchParams] = useSearchParams()
  const listArgs = useMemo(
    () => parseCanonicalListSearchParams(searchParams),
    [searchParams],
  )
  const { q: listQ, typeFilter, typeFilterParam, sortBy, minMentions, page: currentPage } = listArgs

  const [canonicals, setCanonicals] = useState<CanonicalLocation[]>([])
  const [loading, setLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState(() => searchParams.get("q") ?? "")
  const [projects, setProjects] = useState<Project[]>([])
  const [projectsLoading, setProjectsLoading] = useState(true)
  const [types, setTypes] = useState<string[]>([])
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

  const orderedTypeFilterOptions = useMemo(
    () => sortReviewQueueTypeFilterOptions(types),
    [types],
  )

  useEffect(() => {
    setSearchQuery(searchParams.get("q") ?? "")
  }, [searchParams])

  useEffect(() => {
    const workflowScope = searchParams.get("project_scope")
    const inheritedProject = searchParams.get("project")
    if (workflowScope || !inheritedProject) return
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      const project = next.get("project")
      if (!project || next.get("project_scope")) return next
      next.set("project_scope", project)
      next.delete("project")
      return next
    }, { replace: true })
  }, [searchParams, setSearchParams])

  useEffect(() => {
    const urlQ = searchParams.get("q") ?? ""
    const timer = setTimeout(() => {
      if (searchQuery === urlQ) return
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev)
        const trimmed = searchQuery.trim()
        if (trimmed) next.set("q", trimmed)
        else next.delete("q")
        next.delete("page")
        return next
      })
    }, 300)
    return () => clearTimeout(timer)
  }, [searchQuery, searchParams, setSearchParams])

  useEffect(() => {
    let cancelled = false
    setProjectsLoading(true)
    void fetchProjects()
      .then((rows) => {
        if (!cancelled) setProjects(rows)
      })
      .catch(() => {
        if (!cancelled) setProjects([])
      })
      .finally(() => {
        if (!cancelled) setProjectsLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

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

  const setTypeFilterParam = useCallback(
    (value: string) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev)
        if (value === "all") next.delete("type")
        else next.set("type", value)
        next.delete("page")
        return next
      })
    },
    [setSearchParams],
  )

  const setProjectFilterParam = useCallback(
    (value: string) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev)
        if (value === "all-projects") next.delete("project")
        else {
          next.set("project", value)
          if (!next.get("project_scope")) {
            next.set("project_scope", projectScopeSlug || value)
          }
        }
        next.delete("page")
        return next
      })
    },
    [projectScopeSlug, setSearchParams],
  )

  const setSortParam = useCallback(
    (value: CanonicalListSort) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev)
        if (value === "label") next.delete("sort")
        else next.set("sort", "recent")
        next.delete("page")
        return next
      })
    },
    [setSearchParams],
  )

  const setMinMentionsParam = useCallback(
    (n: number) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev)
        if (n <= 0) next.delete("min_mentions")
        else next.set("min_mentions", String(n))
        next.delete("page")
        return next
      })
    },
    [setSearchParams],
  )

  const loadCanonicals = async (
    slug: string,
    q?: string,
    page: number = 1,
    tf?: string,
    listSort: CanonicalListSort = "label",
    mentionsMin: number = 0,
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
        { sort: listSort, minMentions: mentionsMin },
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
      listQ || undefined,
      currentPage,
      typeFilterParam,
      sortBy,
      minMentions,
    )
  }, [currentPage, stylebookSlug, listQ, typeFilterParam, projectFilterSlug, sortBy, minMentions])

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
          <Link to={`${catalogBasePath}/locations/candidates${filterScopeSuffix}`}>
            <Button variant="outline">Candidates</Button>
          </Link>
          <Link to={`${catalogBasePath}/locations/create${filterScopeSuffix}`}>
            <Button variant="outline">Create</Button>
          </Link>
          <Link to={`${catalogBasePath}/import/locations${filterScopeSuffix}`}>
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
                <Select value={typeFilter} onValueChange={setTypeFilterParam}>
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
              <div>
                <Label>Project</Label>
                <Select
                  value={projectFilterSlug || "all-projects"}
                  onValueChange={setProjectFilterParam}
                  disabled={projectsLoading}
                >
                  <SelectTrigger>
                    <SelectValue placeholder={projectsLoading ? "Loading…" : "All projects"} />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all-projects">All projects</SelectItem>
                    {projects.map((project) => (
                      <SelectItem key={project.id} value={project.slug}>
                        {project.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label htmlFor="min-mentions">Minimum mentions</Label>
                <Input
                  id="min-mentions"
                  type="number"
                  min={0}
                  step={1}
                  value={minMentions === 0 ? "" : String(minMentions)}
                  placeholder="0"
                  onChange={(e) => {
                    const raw = e.target.value
                    if (raw === "") {
                      setMinMentionsParam(0)
                      return
                    }
                    const n = parseInt(raw, 10)
                    if (!Number.isNaN(n) && n >= 0) setMinMentionsParam(n)
                  }}
                />
              </div>
              <div>
                <Label>Sort by</Label>
                <Select
                  value={sortBy}
                  onValueChange={(v) => setSortParam(v as CanonicalListSort)}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="label">Name (A–Z)</SelectItem>
                    <SelectItem value="recent">Recently active</SelectItem>
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
                      setSearchParams((prev) => {
                        const next = new URLSearchParams(prev)
                        if (page <= 1) next.delete("page")
                        else next.set("page", String(page))
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
                            <CardTitle>
                              <Link
                                to={{
                                  pathname: `${catalogBasePath}/locations/canonical/${c.id}`,
                                  search: searchParams.toString() ? `?${searchParams.toString()}` : "",
                                }}
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
                      setSearchParams((prev) => {
                        const next = new URLSearchParams(prev)
                        if (page <= 1) next.delete("page")
                        else next.set("page", String(page))
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
                    listQ || undefined,
                    currentPage,
                    typeFilterParam,
                    sortBy,
                    minMentions,
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
