import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { Link, useParams } from "react-router-dom"
import { Breadcrumbs } from "@/components/Breadcrumbs"
import { DuplicateClusterList } from "@/components/DuplicateClusterList"
import { StylebookHomeTabs } from "@/components/StylebookHomeTabs"
import Pagination from "@/components/Pagination"
import { useAppMessage } from "@/components/AppMessageProvider"
import { Loader2 } from "lucide-react"
import { useProjectCatalogScope } from "@/lib/catalogNavigation"
import { useScopeBreadcrumbRoot } from "@/lib/breadcrumbs"
import {
  cleanupCheckConfigById,
  cleanupEntityDetailPath,
  cleanupLinkedRecordLabel,
  cleanupLinkedRecordSingular,
  type CleanupEntityType,
} from "@/lib/cleanupChecks"
import {
  applyDeleteEmptyToClusterResults,
  applyMergeToClusterResults,
  assignStableClusterIds,
} from "@/lib/cleanupClusterState"
import {
  deleteEmptyCleanupLocationCanonical,
  deleteEmptyCleanupOrganizationCanonical,
  deleteEmptyCleanupPersonCanonical,
  getCleanupCheckResults,
  mergeCleanupLocationCanonical,
  mergeCleanupOrganizationCanonical,
  mergeCleanupPersonCanonical,
  type CanonicalLocation,
  type PaginatedDuplicateClustersResponse,
  type PaginatedCanonicalLocationResponse,
} from "@/lib/api"
import { useCanEditStylebook } from "@/lib/stylebookEditContext"
import { placeExtractTypeLabel } from "@/lib/place-extract-type-label"

const PER_PAGE = 25

async function mergeCleanupCanonical(
  entityType: CleanupEntityType,
  stylebookSlug: string,
  sourceId: string,
  targetId: string,
) {
  switch (entityType) {
    case "person":
      return mergeCleanupPersonCanonical(stylebookSlug, sourceId, targetId)
    case "organization":
      return mergeCleanupOrganizationCanonical(stylebookSlug, sourceId, targetId)
    default:
      return mergeCleanupLocationCanonical(stylebookSlug, sourceId, targetId)
  }
}

async function deleteEmptyCleanupCanonical(
  entityType: CleanupEntityType,
  stylebookSlug: string,
  canonicalId: string,
) {
  switch (entityType) {
    case "person":
      return deleteEmptyCleanupPersonCanonical(stylebookSlug, canonicalId)
    case "organization":
      return deleteEmptyCleanupOrganizationCanonical(stylebookSlug, canonicalId)
    default:
      return deleteEmptyCleanupLocationCanonical(stylebookSlug, canonicalId)
  }
}

function entitySingular(entityType: CleanupEntityType): string {
  switch (entityType) {
    case "person":
      return "person"
    case "organization":
      return "organization"
    default:
      return "location"
  }
}

export default function CleanupCheck() {
  const { checkId = "" } = useParams<{ checkId: string }>()
  const config = cleanupCheckConfigById(checkId)
  const { showConfirm, showError, showMessage } = useAppMessage()
  const canEdit = useCanEditStylebook()
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
  const clusterStableIdByMemberRef = useRef<Map<string, string>>(new Map())
  const nextClusterStableIdRef = useRef(0)

  const entityType = config?.entityType ?? "location"
  const linkedRecordLabel = cleanupLinkedRecordLabel(entityType)
  const linkedRecordSingular = cleanupLinkedRecordSingular(entityType)

  const detailHref = useCallback(
    (canonicalId: string) =>
      cleanupEntityDetailPath(catalogBasePath, entityType, canonicalId, catalogScopeSuffix),
    [catalogBasePath, catalogScopeSuffix, entityType],
  )

  useEffect(() => {
    setPage(1)
  }, [checkId, projectFilterSlug])

  const loadResults = useCallback(async () => {
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
      if (config.kind === "cluster") {
        const paginated = response as PaginatedDuplicateClustersResponse
        setClusterResults({
          ...paginated,
          clusters: assignStableClusterIds(
            paginated.clusters,
            clusterStableIdByMemberRef.current,
            nextClusterStableIdRef,
          ),
        })
        setListResults(null)
      } else {
        setListResults(response as PaginatedCanonicalLocationResponse)
        setClusterResults(null)
      }
    } catch (error) {
      showError(error instanceof Error ? error.message : "Failed to load cleanup results")
    } finally {
      setLoading(false)
    }
  }, [stylebookSlug, checkId, config, projectFilterSlug, page, showError])

  useEffect(() => {
    void loadResults()
  }, [loadResults])

  const findCanonicalLabel = useCallback(
    (canonicalId: string): string | undefined => {
      for (const cluster of clusterResults?.clusters ?? []) {
        const match = cluster.canonicals.find((canonical) => canonical.id === canonicalId)
        if (match) return match.label
      }
      return undefined
    },
    [clusterResults],
  )

  const handleMerge = useCallback(
    async (sourceId: string, targetId: string) => {
      if (!stylebookSlug) return
      const sourceLabel = findCanonicalLabel(sourceId) ?? "this record"
      const targetLabel = findCanonicalLabel(targetId) ?? "the other record"
      const confirmed = await showConfirm(
        `Move all ${linkedRecordLabel} from "${sourceLabel}" into "${targetLabel}" and delete the duplicate record?`,
        {
          title: `Merge ${entitySingular(entityType)}s?`,
          confirmLabel: "Merge",
        },
      )
      if (!confirmed) return
      try {
        const result = await mergeCleanupCanonical(
          entityType,
          stylebookSlug,
          sourceId,
          targetId,
        )
        const moved = result.relinked_substrate_count
        showMessage(
          moved > 0
            ? `Merged ${moved} ${moved === 1 ? linkedRecordSingular : linkedRecordLabel} into "${targetLabel}".`
            : `Removed duplicate record "${sourceLabel}".`,
        )
        setClusterResults((prev) =>
          prev
            ? applyMergeToClusterResults(prev, sourceId, targetId, result.relinked_substrate_count)
            : prev,
        )
      } catch (error) {
        showError(
          error instanceof Error
            ? error.message
            : `Failed to merge ${entitySingular(entityType)}s`,
        )
      }
    },
    [
      stylebookSlug,
      entityType,
      linkedRecordLabel,
      linkedRecordSingular,
      findCanonicalLabel,
      showConfirm,
      showMessage,
      showError,
    ],
  )

  const handleDeleteEmpty = useCallback(
    async (canonicalId: string) => {
      if (!stylebookSlug) return
      const label = findCanonicalLabel(canonicalId) ?? "this record"
      const confirmed = await showConfirm(`Delete empty ${entitySingular(entityType)} "${label}"?`, {
        title: `Delete ${entitySingular(entityType)}?`,
        confirmLabel: "Delete",
        destructive: true,
      })
      if (!confirmed) return
      try {
        await deleteEmptyCleanupCanonical(entityType, stylebookSlug, canonicalId)
        showMessage(`Deleted "${label}".`)
        setClusterResults((prev) =>
          prev ? applyDeleteEmptyToClusterResults(prev, canonicalId) : prev,
        )
      } catch (error) {
        showError(
          error instanceof Error
            ? error.message
            : `Failed to delete ${entitySingular(entityType)}`,
        )
      }
    },
    [stylebookSlug, entityType, findCanonicalLabel, showConfirm, showMessage, showError],
  )

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
          clusters={clusterResults?.clusters ?? []}
          entityType={entityType}
          detailHref={detailHref}
          linkedRecordLabel={linkedRecordLabel}
          canEdit={canEdit}
          onMerge={canEdit ? handleMerge : undefined}
          onDeleteEmpty={canEdit ? handleDeleteEmpty : undefined}
        />
      ) : (
        <MissingGeometryList
          canonicals={listResults?.canonicals ?? []}
          locationDetailHref={detailHref}
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
