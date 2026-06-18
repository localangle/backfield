import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { Link, useParams } from "react-router-dom"
import { Breadcrumbs } from "@/components/Breadcrumbs"
import { CleanupAiReviewDialog } from "@/components/CleanupAiReviewDialog"
import { DuplicateClusterList } from "@/components/DuplicateClusterList"
import { StylebookHomeTabs } from "@/components/StylebookHomeTabs"
import Pagination from "@/components/Pagination"
import { Button } from "@/components/ui/button"
import { useAppMessage } from "@/components/AppMessageProvider"
import { Loader2, Sparkles } from "lucide-react"
import { useProjectCatalogScope } from "@/lib/catalogNavigation"
import { useScopeBreadcrumbRoot } from "@/lib/breadcrumbs"
import { CLEANUP_AI_HIGH_CONFIDENCE_THRESHOLD } from "@/lib/cleanupAiReview"
import { useCleanupAiReviewPolling } from "@/hooks/useCleanupAiReviewPolling"
import {
  cleanupCheckConfigById,
  cleanupEntityDetailPath,
  cleanupLinkedRecordLabel,
  cleanupLinkedRecordSingular,
  type CleanupEntityType,
} from "@/lib/cleanupChecks"
import {
  applyDeleteEmptyToClusterResults,
  applyDismissCanonicalToListResults,
  applyDismissClusterToResults,
  applyMergeToClusterResults,
  assignStableClusterIds,
} from "@/lib/cleanupClusterState"
import {
  deleteEmptyCleanupLocationCanonical,
  deleteEmptyCleanupOrganizationCanonical,
  deleteEmptyCleanupPersonCanonical,
  dismissCleanupIssue,
  getCleanupCheckResults,
  mergeCleanupLocationCanonical,
  mergeCleanupOrganizationCanonical,
  mergeCleanupPersonCanonical,
  acceptCleanupAiProposal,
  rejectCleanupAiProposal,
  type CleanupAiProposal,
  type CleanupLocationIssue,
  type PaginatedDuplicateClustersResponse,
  type PaginatedCleanupLocationIssuesResponse,
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
    useState<PaginatedCleanupLocationIssuesResponse | null>(null)
  const clusterStableIdByMemberRef = useRef<Map<string, string>>(new Map())
  const nextClusterStableIdRef = useRef(0)
  const [aiDialogOpen, setAiDialogOpen] = useState(false)
  const isClusterCheck = config?.kind === "cluster"

  const {
    review: aiReview,
    proposals: aiProposals,
    startTracking: startAiReviewTracking,
    removeProposal: removeAiProposal,
  } = useCleanupAiReviewPolling({
    stylebookSlug,
    checkId: config?.id ?? "",
    enabled: Boolean(stylebookSlug && isClusterCheck),
  })

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
        setListResults(response as PaginatedCleanupLocationIssuesResponse)
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
    [stylebookSlug, entityType, findCanonicalLabel, showConfirm, showError],
  )

  const handleDismissCluster = useCallback(
    async (clusterId: string, memberIds: string[]) => {
      if (!stylebookSlug || !config) return
      const confirmed = await showConfirm(
        "These records will stay separate and this group will be removed from cleanup. New matches may appear later if additional similar records are added.",
        {
          title: "Keep separate?",
          confirmLabel: "Keep separate",
        },
      )
      if (!confirmed) return
      try {
        await dismissCleanupIssue({
          stylebookSlug,
          checkId: config.id,
          memberIds,
        })
        setClusterResults((prev) =>
          prev ? applyDismissClusterToResults(prev, clusterId) : prev,
        )
      } catch (error) {
        showError(
          error instanceof Error ? error.message : "Failed to dismiss duplicate group",
        )
      }
    },
    [stylebookSlug, config, showConfirm, showError],
  )

  const handleDismissGeographyIssue = useCallback(
    async (canonicalId: string) => {
      if (!stylebookSlug || !config) return
      const label =
        listResults?.canonicals.find((canonical) => canonical.id === canonicalId)?.label ??
        "this location"
      const confirmed = await showConfirm(
        `Remove "${label}" from this cleanup list? It may reappear if the underlying issue remains.`,
        {
          title: "Mark as reviewed?",
          confirmLabel: "Mark reviewed",
        },
      )
      if (!confirmed) return
      try {
        await dismissCleanupIssue({
          stylebookSlug,
          checkId: config.id,
          canonicalId,
        })
        setListResults((prev) =>
          prev ? applyDismissCanonicalToListResults(prev, canonicalId) : prev,
        )
      } catch (error) {
        showError(
          error instanceof Error ? error.message : "Failed to dismiss geography issue",
        )
      }
    },
    [stylebookSlug, config, listResults, showConfirm, showError],
  )

  const applyAcceptedMergeProposal = useCallback(
    (proposal: CleanupAiProposal) => {
      if (proposal.action !== "merge" || !proposal.target_canonical_id) return
      setClusterResults((prev) => {
        if (!prev) return prev
        let next = prev
        for (const memberId of proposal.member_ids) {
          if (memberId === proposal.target_canonical_id) continue
          next = applyMergeToClusterResults(next, memberId, proposal.target_canonical_id, 0)
        }
        return next
      })
    },
    [],
  )

  const handleAcceptAiProposal = useCallback(
    async (proposal: CleanupAiProposal) => {
      if (!stylebookSlug) return
      try {
        const result = await acceptCleanupAiProposal({
          stylebookSlug,
          proposalId: proposal.id,
        })
        if (result.status === "stale") {
          showError(result.message)
        } else if (proposal.action === "merge") {
          applyAcceptedMergeProposal(proposal)
        }
        removeAiProposal(proposal.id)
      } catch (error) {
        showError(error instanceof Error ? error.message : "Failed to accept AI suggestion")
      }
    },
    [stylebookSlug, showError, applyAcceptedMergeProposal, removeAiProposal],
  )

  const handleRejectAiProposal = useCallback(
    async (proposal: CleanupAiProposal) => {
      if (!stylebookSlug) return
      try {
        await rejectCleanupAiProposal({ stylebookSlug, proposalId: proposal.id })
        removeAiProposal(proposal.id)
      } catch (error) {
        showError(error instanceof Error ? error.message : "Failed to reject AI suggestion")
      }
    },
    [stylebookSlug, showError, removeAiProposal],
  )

  const highConfidenceProposals = useMemo(
    () =>
      aiProposals.filter(
        (proposal) => proposal.confidence >= CLEANUP_AI_HIGH_CONFIDENCE_THRESHOLD,
      ),
    [aiProposals],
  )

  const handleAcceptAllHighConfidence = useCallback(async () => {
    if (!stylebookSlug || highConfidenceProposals.length === 0) return
    for (const proposal of highConfidenceProposals) {
      try {
        const result = await acceptCleanupAiProposal({
          stylebookSlug,
          proposalId: proposal.id,
        })
        if (result.status === "applied" && proposal.action === "merge") {
          applyAcceptedMergeProposal(proposal)
        } else if (result.status === "stale") {
          showError(result.message)
        }
        removeAiProposal(proposal.id)
      } catch {
        // Continue with remaining proposals.
      }
    }
  }, [
    stylebookSlug,
    highConfidenceProposals,
    showError,
    applyAcceptedMergeProposal,
    removeAiProposal,
  ])

  const handleReviewStarted = useCallback(
    (reviewId: string) => {
      void startAiReviewTracking(reviewId)
      showMessage("AI review started. Suggestions will appear when it finishes.")
    },
    [startAiReviewTracking, showMessage],
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

      {canEdit && isClusterCheck ? (
        <div className="flex flex-wrap items-center gap-2">
          <Button type="button" variant="outline" onClick={() => setAiDialogOpen(true)}>
            <Sparkles className="h-4 w-4 mr-2" />
            Review with AI
          </Button>
          {aiReview && (aiReview.status === "queued" || aiReview.status === "running") ? (
            <span className="text-sm text-muted-foreground inline-flex items-center gap-2">
              <Loader2 className="h-4 w-4 animate-spin" />
              Reviewing clusters ({aiReview.processed_cluster_count}/{aiReview.cluster_count})…
            </span>
          ) : null}
          {aiReview?.status === "failed" ? (
            <span className="text-sm text-destructive">
              AI review failed{aiReview.error_message ? `: ${aiReview.error_message}` : "."}
            </span>
          ) : null}
          {highConfidenceProposals.length > 0 ? (
            <Button type="button" size="sm" onClick={() => void handleAcceptAllHighConfidence()}>
              Accept all high-confidence ({highConfidenceProposals.length})
            </Button>
          ) : null}
        </div>
      ) : null}

      {canEdit && isClusterCheck ? (
        <CleanupAiReviewDialog
          open={aiDialogOpen}
          onOpenChange={setAiDialogOpen}
          stylebookSlug={stylebookSlug}
          checkId={config.id}
          onReviewStarted={handleReviewStarted}
        />
      ) : null}

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
          aiProposals={aiProposals}
          onMerge={canEdit ? handleMerge : undefined}
          onDeleteEmpty={canEdit ? handleDeleteEmpty : undefined}
          onDismissCluster={canEdit ? handleDismissCluster : undefined}
          onAcceptAiProposal={canEdit ? handleAcceptAiProposal : undefined}
          onRejectAiProposal={canEdit ? handleRejectAiProposal : undefined}
        />
      ) : (
        <GeographyIssuesList
          canonicals={listResults?.canonicals ?? []}
          locationDetailHref={detailHref}
          canEdit={canEdit}
          onDismiss={canEdit ? handleDismissGeographyIssue : undefined}
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

function geographyIssueLabel(issue: CleanupLocationIssue["geography_issue"]): string {
  if (issue === "distant_linked_places") {
    return "Linked place far from catalog geography"
  }
  return "No map geography"
}

function GeographyIssuesList({
  canonicals,
  locationDetailHref,
  canEdit = false,
  onDismiss,
}: {
  canonicals: CleanupLocationIssue[]
  locationDetailHref: (canonicalId: string) => string
  canEdit?: boolean
  onDismiss?: (canonicalId: string) => void | Promise<void>
}) {
  if (canonicals.length === 0) {
    return (
      <p className="text-muted-foreground py-8 text-center">
        No locations with missing or potentially incorrect geographies in this stylebook.
      </p>
    )
  }

  return (
    <div className="rounded-lg border overflow-x-auto">
      <table className="w-full table-fixed text-sm min-w-[40rem]">
        <colgroup>
          <col style={{ width: "28%" }} />
          <col style={{ width: "22%" }} />
          <col style={{ width: "12%" }} />
          <col style={{ width: "10%" }} />
          <col style={{ width: "8%" }} />
          <col style={{ width: "8%" }} />
          {canEdit && onDismiss ? <col style={{ width: "12%" }} /> : null}
        </colgroup>
        <thead className="bg-muted/50 text-left">
          <tr>
            <th className="px-4 py-3 font-medium min-w-0">Name</th>
            <th className="px-4 py-3 font-medium min-w-0">Issue</th>
            <th className="px-4 py-3 font-medium min-w-0">Type</th>
            <th className="px-4 py-3 font-medium min-w-0">Status</th>
            <th className="px-4 py-3 font-medium text-right">Linked</th>
            <th className="px-4 py-3 font-medium text-right">Mentions</th>
            {canEdit && onDismiss ? (
              <th className="px-4 py-3 font-medium text-right">Action</th>
            ) : null}
          </tr>
        </thead>
        <tbody>
          {canonicals.map((canonical) => (
            <tr key={canonical.id} className="border-t hover:bg-muted/30">
              <td className="px-4 py-3 min-w-0">
                <Link
                  to={locationDetailHref(canonical.id)}
                  className="font-medium text-primary hover:underline block truncate"
                  title={canonical.label}
                >
                  {canonical.label}
                </Link>
              </td>
              <td className="px-4 py-3 text-muted-foreground min-w-0">
                <span className="block truncate" title={geographyIssueLabel(canonical.geography_issue)}>
                  {geographyIssueLabel(canonical.geography_issue)}
                  {canonical.geography_issue === "distant_linked_places" &&
                  (canonical.distant_linked_count ?? 0) > 0
                    ? ` (${canonical.distant_linked_count})`
                    : null}
                </span>
              </td>
              <td className="px-4 py-3 text-muted-foreground min-w-0">
                <span className="block truncate">
                  {canonical.location_type
                    ? placeExtractTypeLabel(canonical.location_type)
                    : "—"}
                </span>
              </td>
              <td className="px-4 py-3 text-muted-foreground min-w-0">
                <span className="block truncate">{canonical.status}</span>
              </td>
              <td className="px-4 py-3 text-right tabular-nums">
                {canonical.linked_substrate_count ?? 0}
              </td>
              <td className="px-4 py-3 text-right tabular-nums">
                {canonical.mention_count ?? 0}
              </td>
              {canEdit && onDismiss ? (
                <td className="px-4 py-3 text-right">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => void onDismiss(canonical.id)}
                  >
                    Mark reviewed
                  </Button>
                </td>
              ) : null}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
