import { useCallback, useEffect, useMemo, useState } from "react"
import { Link, useParams } from "react-router-dom"
import { Breadcrumbs } from "@/components/Breadcrumbs"
import { DuplicateClusterList } from "@/components/DuplicateClusterList"
import { StylebookHomeTabs } from "@/components/StylebookHomeTabs"
import Pagination from "@/components/Pagination"
import { useAppMessage } from "@/components/AppMessageProvider"
import { Loader2 } from "lucide-react"
import { useProjectCatalogScope } from "@/lib/catalogNavigation"
import { useScopeBreadcrumbRoot } from "@/lib/breadcrumbs"
import { cleanupCheckConfigById } from "@/lib/cleanupChecks"
import {
  getCleanupCheckResults,
  type CanonicalLocation,
  type DuplicateLocationCluster,
  type PaginatedDuplicateClustersResponse,
  type PaginatedCanonicalLocationResponse,
} from "@/lib/api"
import { placeExtractTypeLabel } from "@/lib/place-extract-type-label"

const PER_PAGE = 25

export default function CleanupCheck() {
  const { checkId = "" } = useParams<{ checkId: string }>()
  const config = cleanupCheckConfigById(checkId)
  const { showError } = useAppMessage()
  const {
    stylebookSlug,
    catalogBasePath,
    catalogScopeSuffix,
    projectFilterSlug,
  } = useProjectCatalogScope()
  const crumbRoot = useScopeBreadcrumbRoot()
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [clusterResults, setClusterResults] =
    useState<PaginatedDuplicateClustersResponse | null>(null)
  const [listResults, setListResults] =
    useState<PaginatedCanonicalLocationResponse | null>(null)

  const locationDetailHref = useCallback(
    (canonicalId: string) =>
      `${catalogBasePath}/locations/canonical/${encodeURIComponent(canonicalId)}${catalogScopeSuffix}`,
    [catalogBasePath, catalogScopeSuffix],
  )

  useEffect(() => {
    setPage(1)
  }, [checkId, projectFilterSlug])

  useEffect(() => {
    let cancelled = false
    async function load() {
      if (!stylebookSlug || !config) return
      setLoading(true)
      try {
        const response = await getCleanupCheckResults({
          stylebookSlug,
          checkId,
          project: projectFilterSlug || undefined,
          page,
          perPage: PER_PAGE,
        })
        if (cancelled) return
        if (config.kind === "cluster") {
          setClusterResults(response as PaginatedDuplicateClustersResponse)
          setListResults(null)
        } else {
          setListResults(response as PaginatedCanonicalLocationResponse)
          setClusterResults(null)
        }
      } catch (error) {
        if (!cancelled) {
          showError(error instanceof Error ? error.message : "Failed to load cleanup results")
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [stylebookSlug, checkId, config, projectFilterSlug, page, showError])

  const pagination = useMemo(() => {
    if (clusterResults) {
      return {
        page: clusterResults.page,
        total: clusterResults.total,
        hasNext: clusterResults.has_next,
        hasPrev: clusterResults.has_prev,
      }
    }
    if (listResults) {
      return {
        page: listResults.page,
        total: listResults.total,
        hasNext: listResults.has_next,
        hasPrev: listResults.has_prev,
      }
    }
    return { page: 1, total: 0, hasNext: false, hasPrev: false }
  }, [clusterResults, listResults])

  if (!config) {
    return (
      <div className="space-y-4">
        <p className="text-muted-foreground">Unknown cleanup check.</p>
        <Link
          to={`${catalogBasePath}/cleanup${catalogScopeSuffix}`}
          className="text-primary hover:underline"
        >
          Back to cleanup
        </Link>
      </div>
    )
  }

  const cleanupHubPath = `${catalogBasePath}/cleanup${catalogScopeSuffix}`

  return (
    <div className="space-y-6">
      <div>
        <Breadcrumbs
          items={[
            { label: crumbRoot.label, to: `${catalogBasePath}${catalogScopeSuffix}` },
            { label: "Cleanup", to: cleanupHubPath },
            { label: config.title },
          ]}
          className="mb-3"
        />
        <h1 className="text-3xl font-bold">{config.title}</h1>
        <p className="text-muted-foreground mt-2">{config.description}</p>
      </div>

      <StylebookHomeTabs />

      {loading ? (
        <div className="flex items-center gap-2 text-muted-foreground py-8">
          <Loader2 className="h-5 w-5 animate-spin" />
          Loading…
        </div>
      ) : config.kind === "cluster" ? (
        <DuplicateClusterList
          clusters={(clusterResults?.clusters ?? []) as DuplicateLocationCluster[]}
          locationDetailHref={locationDetailHref}
        />
      ) : (
        <MissingGeometryList
          canonicals={listResults?.canonicals ?? []}
          locationDetailHref={locationDetailHref}
        />
      )}

      {!loading && pagination.total > PER_PAGE ? (
        <Pagination
          page={pagination.page}
          perPage={PER_PAGE}
          total={pagination.total}
          totalPages={Math.max(1, Math.ceil(pagination.total / PER_PAGE))}
          hasNext={pagination.hasNext}
          hasPrev={pagination.hasPrev}
          onPageChange={setPage}
          itemLabel={config.kind === "cluster" ? "clusters" : "locations"}
        />
      ) : null}
    </div>
  )
}

function MissingGeometryList({
  canonicals,
  locationDetailHref,
}: {
  canonicals: CanonicalLocation[]
  locationDetailHref: (canonicalId: string) => string
}) {
  if (canonicals.length === 0) {
    return (
      <p className="text-muted-foreground py-8 text-center">
        No locations missing geography in this stylebook.
      </p>
    )
  }

  return (
    <div className="border rounded-lg overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-muted/50 text-left">
          <tr>
            <th className="px-4 py-3 font-medium">Name</th>
            <th className="px-4 py-3 font-medium">Type</th>
            <th className="px-4 py-3 font-medium">Status</th>
            <th className="px-4 py-3 font-medium text-right">Linked</th>
            <th className="px-4 py-3 font-medium text-right">Mentions</th>
          </tr>
        </thead>
        <tbody>
          {canonicals.map((canonical) => (
            <tr key={canonical.id} className="border-t hover:bg-muted/30">
              <td className="px-4 py-3">
                <Link
                  to={locationDetailHref(canonical.id)}
                  className="font-medium text-primary hover:underline"
                >
                  {canonical.label}
                </Link>
              </td>
              <td className="px-4 py-3 text-muted-foreground">
                {canonical.location_type
                  ? placeExtractTypeLabel(canonical.location_type)
                  : "—"}
              </td>
              <td className="px-4 py-3 text-muted-foreground">{canonical.status}</td>
              <td className="px-4 py-3 text-right tabular-nums">
                {canonical.linked_substrate_count ?? 0}
              </td>
              <td className="px-4 py-3 text-right tabular-nums">
                {canonical.mention_count ?? 0}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
