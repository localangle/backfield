import { useEffect, useMemo, useState } from "react"
import { Link } from "react-router-dom"
import { useAppMessage } from "@/components/AppMessageProvider"
import { useProjectCatalogScope } from "@/lib/catalogNavigation"
import { useScopeBreadcrumbRoot } from "@/lib/breadcrumbs"
import { fetchProjects, type Project } from "@/lib/api"
import { placeExtractTypeLabel, sortReviewQueueTypeFilterOptions } from "@/lib/place-extract-type-label"
import type {
  CanonicalListBaseUrlState,
  CanonicalListPageConfig,
} from "@/lib/entityConfigs/canonicalListTypes"
import { useCanonicalListUrlState } from "@/lib/useCanonicalListUrlState"
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

type CanonicalListPageProps<
  TCanonical extends { id: string; label: string },
  TSort extends string,
  TUrlState extends CanonicalListBaseUrlState<TSort>,
> = {
  config: CanonicalListPageConfig<TCanonical, TSort, TUrlState>
}

export function CanonicalListPage<
  TCanonical extends { id: string; label: string },
  TSort extends string,
  TUrlState extends CanonicalListBaseUrlState<TSort>,
>({ config }: CanonicalListPageProps<TCanonical, TSort, TUrlState>) {
  const { showError } = useAppMessage()
  const { filterScopeSuffix, stylebookSlug, catalogBasePath } = useProjectCatalogScope()
  const crumbRoot = useScopeBreadcrumbRoot()
  const canEdit = useCanEditStylebook()
  const perPage = config.perPage ?? 25

  const {
    searchParams,
    urlState,
    searchQuery,
    setSearchQuery,
    textQueries,
    setTextQuery,
    setSelectParam,
    setTypeFilterParam,
    setProjectFilterParam,
    setSortParam,
    setMinMentionsParam,
    setPageParam,
    projectFilterSlug,
  } = useCanonicalListUrlState<TSort, TUrlState>({
    parseListArgs: config.parseListArgs,
    extraDebouncedParamKeys: config.extraDebouncedParamKeys,
    sortToUrlParam: config.sortToUrlParam,
  })

  const { typeFilter, sortBy, minMentions, page: currentPage } = urlState

  const [canonicals, setCanonicals] = useState<TCanonical[]>([])
  const [loading, setLoading] = useState(true)
  const [projects, setProjects] = useState<Project[]>([])
  const [projectsLoading, setProjectsLoading] = useState(true)
  const [types, setTypes] = useState<string[]>([])
  const [total, setTotal] = useState(0)
  const [hasNext, setHasNext] = useState(false)
  const [hasPrev, setHasPrev] = useState(false)
  const [deleteDialog, setDeleteDialog] = useState<{ open: boolean; row: TCanonical | null }>({
    open: false,
    row: null,
  })
  const [deleting, setDeleting] = useState(false)

  const orderedTypeFilterOptions = useMemo(
    () => sortReviewQueueTypeFilterOptions(types),
    [types],
  )

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
        const res = await config.fetchTypes(stylebookSlug)
        setTypes(res.types)
      } catch {
        setTypes([])
      }
    })()
  }, [stylebookSlug, config])

  const loadCanonicals = async () => {
    if (!stylebookSlug) return
    try {
      setLoading(true)
      const data = await config.fetchCanonicals(
        stylebookSlug,
        projectFilterSlug || undefined,
        urlState,
        perPage,
      )
      setCanonicals(data.canonicals)
      setTotal(data.total)
      setHasNext(data.has_next)
      setHasPrev(data.has_prev)
    } catch (error) {
      console.error("Failed to load canonicals:", error)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!stylebookSlug) return
    void loadCanonicals()
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reload when URL-derived list args change
  }, [stylebookSlug, projectFilterSlug, urlState, perPage])

  const filterContext = {
    urlState,
    textQueries,
    setTextQuery,
    setSelectParam,
    setTypeFilterParam,
    setProjectFilterParam,
    setSortParam,
    setMinMentionsParam,
    projects,
    projectsLoading,
    orderedTypeOptions: orderedTypeFilterOptions,
    projectFilterSlug,
  }

  const searchPlaceholder =
    config.routeSegment === "people" || config.routeSegment === "organizations"
      ? "Search names…"
      : "Search canonical labels…"

  return (
    <div className="container mx-auto p-6">
      <div className="flex justify-between items-center mb-6">
        <div className="min-w-0">
          <Breadcrumbs
            className="mb-3"
            items={[
              { label: crumbRoot.label, to: crumbRoot.to },
              { label: config.breadcrumbLabel },
            ]}
          />
          <h1 className="text-3xl font-bold">{config.pageTitle}</h1>
        </div>
        <div className="flex gap-2">
          <Link to={`${catalogBasePath}/${config.routeSegment}/candidates${filterScopeSuffix}`}>
            <Button variant="outline">Candidates</Button>
          </Link>
          <Link to={`${catalogBasePath}/${config.routeSegment}/create${filterScopeSuffix}`}>
            <Button variant="outline">Create</Button>
          </Link>
          <Link to={`${catalogBasePath}/import/${config.routeSegment}${filterScopeSuffix}`}>
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
                  placeholder={searchPlaceholder}
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                />
              </div>
              {config.renderExtraFilters?.(filterContext)}
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
                <Select value={sortBy} onValueChange={(v) => setSortParam(v as TSort)}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {config.sortOptions.map((opt) => (
                      <SelectItem key={opt.value} value={opt.value}>
                        {opt.label}
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
                {config.emptyMessage}
              </CardContent>
            </Card>
          ) : (
            <>
              {total > perPage && (
                <div className="mb-4">
                  <Pagination
                    page={currentPage}
                    perPage={perPage}
                    total={total}
                    totalPages={Math.ceil(total / perPage)}
                    hasNext={hasNext}
                    hasPrev={hasPrev}
                    onPageChange={setPageParam}
                    itemLabel={config.itemLabel}
                  />
                </div>
              )}
              <div className="grid gap-4">
                {canonicals.map((c) => (
                  <Card key={c.id}>
                    <CardHeader>
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <CardTitle>
                            <Link
                              to={{
                                pathname: config.detailPath(catalogBasePath, c.id),
                                search: searchParams.toString() ? `?${searchParams.toString()}` : "",
                              }}
                              className="hover:underline"
                            >
                              {c.label}
                            </Link>
                          </CardTitle>
                          <CardDescription>{config.renderRowDescription(c)}</CardDescription>
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
              {total > perPage && (
                <div className="mt-4">
                  <Pagination
                    page={currentPage}
                    perPage={perPage}
                    total={total}
                    totalPages={Math.ceil(total / perPage)}
                    hasNext={hasNext}
                    hasPrev={hasPrev}
                    onPageChange={setPageParam}
                    itemLabel={config.itemLabel}
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
            <DialogTitle>{config.deleteTitle}</DialogTitle>
            <DialogDescription>
              {deleteDialog.row ? config.deleteDescription(deleteDialog.row.label) : null}
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
                  await config.deleteCanonical(deleteDialog.row.id, stylebookSlug)
                  setDeleteDialog({ open: false, row: null })
                  await loadCanonicals()
                } catch (error) {
                  console.error("Failed to delete canonical:", error)
                  showError(config.deleteErrorMessage)
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
