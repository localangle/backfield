import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { Link, useParams, useSearchParams } from "react-router-dom"
import { Breadcrumbs } from "@/components/Breadcrumbs"
import { CleanupAiReviewDialog } from "@/components/CleanupAiReviewDialog"
import { DuplicateClusterList } from "@/components/DuplicateClusterList"
import { StylebookHomeTabs } from "@/components/StylebookHomeTabs"
import Pagination from "@/components/Pagination"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { useAppMessage } from "@/components/AppMessageProvider"
import { Loader2, Sparkles } from "lucide-react"
import { useProjectCatalogScope } from "@/lib/catalogNavigation"
import { useScopeBreadcrumbRoot } from "@/lib/breadcrumbs"
import { CLEANUP_AI_HIGH_CONFIDENCE_THRESHOLD, isActiveReviewStatus } from "@/lib/cleanupAiReview"
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
  applyKeepSeparateProposalToClusterResults,
  applyMergeToClusterResults,
  assignStableClusterIds,
  pairKeyForIds,
} from "@/lib/cleanupClusterState"
import {
  deleteEmptyCleanupLocationCanonical,
  deleteEmptyCleanupOrganizationCanonical,
  deleteEmptyCleanupPersonCanonical,
  deleteCanonicalPerson,
  deleteCanonicalOrganization,
  dismissCleanupIssue,
  getCleanupCheckResults,
  getLatestCleanupCheckRun,
  listCleanupChecks,
  mergeCleanupLocationCanonical,
  mergeCleanupOrganizationCanonical,
  mergeCleanupPersonCanonical,
  acceptCleanupAiProposal,
  rejectCleanupAiProposal,
  type CleanupAiProposal,
  type CleanupCheckRunStatus,
  type CleanupLocationIssue,
  type CleanupMismatchIssue,
  type CleanupQuestionableOrganizationIssue,
  type CleanupQuestionablePersonIssue,
  type PaginatedDuplicateClustersResponse,
  type PaginatedCleanupListResults,
  type PaginatedCleanupLocationIssuesResponse,
  type PaginatedCleanupMismatchIssuesResponse,
  type PaginatedCleanupQuestionableOrganizationsResponse,
  type PaginatedCleanupQuestionablePeopleResponse,
} from "@/lib/api"
import { useCanEditStylebook } from "@/lib/stylebookEditContext"
import { placeExtractTypeLabel } from "@/lib/place-extract-type-label"

const PER_PAGE = 25
type CleanupQuestionableCanonicalIssue =
  | CleanupQuestionableOrganizationIssue
  | CleanupQuestionablePersonIssue

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
  const { showConfirm, showError } = useAppMessage()
  const canEdit = useCanEditStylebook()
  const {
    stylebookSlug,
    catalogBasePath,
    catalogScopeSuffix,
    projectFilterSlug,
  } = useProjectCatalogScope()
  const crumbRoot = useScopeBreadcrumbRoot()
  const [searchParams, setSearchParams] = useSearchParams()
  const urlQuery = searchParams.get("q") ?? ""
  const [searchQuery, setSearchQuery] = useState(() => urlQuery)
  const [loading, setLoading] = useState(true)
  const [checkRunStatus, setCheckRunStatus] = useState<CleanupCheckRunStatus>("never_run")
  const [page, setPage] = useState(1)
  const [clusterResults, setClusterResults] =
    useState<PaginatedDuplicateClustersResponse | null>(null)
  const [listResults, setListResults] = useState<PaginatedCleanupListResults | null>(null)
  const clusterStableIdByMemberRef = useRef<Map<string, string>>(new Map())
  const nextClusterStableIdRef = useRef(0)
  const dismissedCleanupPairsRef = useRef<Set<string>>(new Set())
  const [aiDialogOpen, setAiDialogOpen] = useState(false)
  const [stoppingAiReview, setStoppingAiReview] = useState(false)
  const [questionableBulkAction, setQuestionableBulkAction] = useState<
    "keep-all" | "delete-all" | null
  >(null)
  const questionableBulkActionRef = useRef<"keep-all" | "delete-all" | null>(null)
  const isClusterCheck = config?.kind === "cluster"

  const {
    review: aiReview,
    proposals: aiProposals,
    startTracking: startAiReviewTracking,
    stopReview: stopAiReview,
    removeProposal: removeAiProposal,
  } = useCleanupAiReviewPolling({
    stylebookSlug,
    checkId: config?.id ?? "",
    enabled: Boolean(stylebookSlug && isClusterCheck),
  })
  const aiReviewActive = Boolean(aiReview && isActiveReviewStatus(aiReview.status))

  async function handleAiReviewButtonClick() {
    if (aiReviewActive) {
      setStoppingAiReview(true)
      try {
        await stopAiReview()
      } finally {
        setStoppingAiReview(false)
      }
      return
    }
    setAiDialogOpen(true)
  }

  const entityType = config?.entityType ?? "location"
  const linkedRecordLabel = cleanupLinkedRecordLabel(entityType)
  const linkedRecordSingular = cleanupLinkedRecordSingular(entityType)

  const detailHref = useCallback(
    (canonicalId: string) =>
      cleanupEntityDetailPath(catalogBasePath, entityType, canonicalId, catalogScopeSuffix),
    [catalogBasePath, catalogScopeSuffix, entityType],
  )

  const refreshHubCheckCount = useCallback(async () => {
    if (!stylebookSlug || !config) return
    try {
      await listCleanupChecks({
        stylebookSlug,
        checkId: config.id,
        project: projectFilterSlug || undefined,
      })
    } catch {
      // Hub refreshes on next visit; ignore background sync failures.
    }
  }, [stylebookSlug, config, projectFilterSlug])

  useEffect(() => {
    if (!stylebookSlug || !config) return
    void getLatestCleanupCheckRun({
      stylebookSlug,
      checkId: config.id,
      project: projectFilterSlug || undefined,
    })
      .then((run) => {
        setCheckRunStatus(run?.status ?? "never_run")
      })
      .catch(() => {
        setCheckRunStatus("never_run")
      })
  }, [stylebookSlug, config, projectFilterSlug])

  useEffect(() => {
    setPage(1)
  }, [checkId, projectFilterSlug, urlQuery])

  useEffect(() => {
    setSearchQuery(urlQuery)
  }, [urlQuery])

  useEffect(() => {
    const handle = window.setTimeout(() => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev)
        const trimmed = searchQuery.trim()
        if (trimmed) next.set("q", trimmed)
        else next.delete("q")
        return next
      })
    }, 300)
    return () => window.clearTimeout(handle)
  }, [searchQuery, setSearchParams])

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
        q: isClusterCheck ? urlQuery || undefined : undefined,
      })
      if (config.kind === "cluster") {
        dismissedCleanupPairsRef.current.clear()
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
        setListResults(response as PaginatedCleanupListResults)
        setClusterResults(null)
      }
    } catch (error) {
      showError(error instanceof Error ? error.message : "Failed to load cleanup results")
    } finally {
      setLoading(false)
    }
  }, [stylebookSlug, checkId, config, projectFilterSlug, page, showError, isClusterCheck, urlQuery])

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
        void refreshHubCheckCount()
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
      refreshHubCheckCount,
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
        void refreshHubCheckCount()
      } catch (error) {
        showError(
          error instanceof Error
            ? error.message
            : `Failed to delete ${entitySingular(entityType)}`,
        )
      }
    },
    [stylebookSlug, entityType, findCanonicalLabel, showConfirm, showError, refreshHubCheckCount],
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
      const sortedMemberIds = [...memberIds].sort()
      for (let index = 0; index < sortedMemberIds.length; index += 1) {
        for (let other = index + 1; other < sortedMemberIds.length; other += 1) {
          dismissedCleanupPairsRef.current.add(
            pairKeyForIds(sortedMemberIds[index], sortedMemberIds[other]),
          )
        }
      }
      try {
        await dismissCleanupIssue({
          stylebookSlug,
          checkId: config.id,
          memberIds,
        })
        setClusterResults((prev) =>
          prev ? applyDismissClusterToResults(prev, clusterId) : prev,
        )
        void refreshHubCheckCount()
      } catch (error) {
        showError(
          error instanceof Error ? error.message : "Failed to dismiss duplicate group",
        )
      }
    },
    [stylebookSlug, config, showConfirm, showError, refreshHubCheckCount],
  )

  const handleDismissListIssue = useCallback(
    async (canonicalId: string) => {
      if (!stylebookSlug || !config) return
      try {
        await dismissCleanupIssue({
          stylebookSlug,
          checkId: config.id,
          canonicalId,
        })
        setListResults((prev) =>
          prev ? applyDismissCanonicalToListResults(prev, canonicalId) : prev,
        )
        void refreshHubCheckCount()
      } catch (error) {
        showError(
          error instanceof Error ? error.message : "Failed to dismiss issue",
        )
      }
    },
    [stylebookSlug, config, showError, refreshHubCheckCount],
  )

  const isQuestionableCanonicalCheck =
    config?.id === "questionable-organization-canonicals" ||
    config?.id === "questionable-person-canonicals"
  const questionableCanonicalResults = useMemo(() => {
    if (!isQuestionableCanonicalCheck) return null
    return listResults as
      | PaginatedCleanupQuestionableOrganizationsResponse
      | PaginatedCleanupQuestionablePeopleResponse
      | null
  }, [isQuestionableCanonicalCheck, listResults])

  const loadAllQuestionableCanonicals = useCallback(async () => {
    if (!stylebookSlug || !config) return []
    const rows: CleanupQuestionableCanonicalIssue[] = []
    let pageNum = 1
    let hasNext = true
    while (hasNext) {
      const response = await getCleanupCheckResults({
        stylebookSlug,
        checkId: config.id,
        project: projectFilterSlug || undefined,
        page: pageNum,
        perPage: 200,
      })
      const paginated = response as
        | PaginatedCleanupQuestionableOrganizationsResponse
        | PaginatedCleanupQuestionablePeopleResponse
      rows.push(...paginated.canonicals)
      hasNext = paginated.has_next
      pageNum += 1
    }
    return rows
  }, [stylebookSlug, config, projectFilterSlug])

  const handleKeepQuestionableCanonical = useCallback(
    async (canonicalId: string) => {
      await handleDismissListIssue(canonicalId)
    },
    [handleDismissListIssue],
  )

  const handleDeleteQuestionableCanonical = useCallback(
    async (canonicalId: string) => {
      if (!stylebookSlug || !config) return
      try {
        if (config.entityType === "person") {
          await deleteCanonicalPerson(canonicalId, stylebookSlug)
        } else {
          await deleteCanonicalOrganization(canonicalId, stylebookSlug)
        }
        setListResults((prev) =>
          prev ? applyDismissCanonicalToListResults(prev, canonicalId) : prev,
        )
        void refreshHubCheckCount()
      } catch (error) {
        showError(
          error instanceof Error
            ? error.message
            : `Failed to delete ${entitySingular(config.entityType)}`,
        )
      }
    },
    [stylebookSlug, config, showError, refreshHubCheckCount],
  )

  const handleKeepAllQuestionableCanonicals = useCallback(async () => {
    if (!stylebookSlug || !config || questionableBulkActionRef.current !== null) return
    questionableBulkActionRef.current = "keep-all"
    setQuestionableBulkAction("keep-all")
    try {
      const rows = await loadAllQuestionableCanonicals()
      if (rows.length === 0) return
      for (const row of rows) {
        await dismissCleanupIssue({
          stylebookSlug,
          checkId: config.id,
          canonicalId: row.id,
        })
      }
      const dismissedIds = new Set(rows.map((row) => row.id))
      setListResults((prev) => {
        if (!prev) return prev
        return {
          ...prev,
          canonicals: (prev.canonicals as CleanupQuestionableCanonicalIssue[]).filter(
            (row) => !dismissedIds.has(row.id),
          ),
          total: Math.max(0, prev.total - rows.length),
        } as PaginatedCleanupListResults
      })
      void refreshHubCheckCount()
    } catch (error) {
      showError(error instanceof Error ? error.message : "Failed to keep records")
    } finally {
      questionableBulkActionRef.current = null
      setQuestionableBulkAction(null)
    }
  }, [stylebookSlug, config, loadAllQuestionableCanonicals, showError, refreshHubCheckCount])

  const handleDeleteAllQuestionableCanonicals = useCallback(async () => {
    if (!stylebookSlug || !config || questionableBulkActionRef.current !== null) return
    questionableBulkActionRef.current = "delete-all"
    setQuestionableBulkAction("delete-all")
    try {
      const rows = await loadAllQuestionableCanonicals()
      if (rows.length === 0) return
      let deleted = 0
      const deletedIds = new Set<string>()
      const failures: string[] = []
      for (const row of rows) {
        try {
          if (config.entityType === "person") {
            await deleteCanonicalPerson(row.id, stylebookSlug)
          } else {
            await deleteCanonicalOrganization(row.id, stylebookSlug)
          }
          deleted += 1
          deletedIds.add(row.id)
        } catch (error) {
          failures.push(
            error instanceof Error ? error.message : `Failed to delete ${row.label}`,
          )
        }
      }
      if (deletedIds.size > 0) {
        setListResults((prev) => {
          if (!prev) return prev
          return {
            ...prev,
            canonicals: (prev.canonicals as CleanupQuestionableCanonicalIssue[]).filter(
              (row) => !deletedIds.has(row.id),
            ),
            total: Math.max(0, prev.total - deletedIds.size),
          } as PaginatedCleanupListResults
        })
      }
      void refreshHubCheckCount()
      if (deleted > 0 && failures.length === 0) {
        return
      }
      if (deleted === 0 && failures.length > 0) {
        showError(failures[0])
        return
      }
      if (failures.length > 0) {
        const singular = entitySingular(config.entityType)
        showError(
          `Deleted ${deleted} ${singular}${deleted === 1 ? "" : "s"}. ${failures.length} could not be deleted.`,
        )
      }
    } catch (error) {
      showError(error instanceof Error ? error.message : "Failed to delete records")
    } finally {
      questionableBulkActionRef.current = null
      setQuestionableBulkAction(null)
    }
  }, [stylebookSlug, config, loadAllQuestionableCanonicals, showError, refreshHubCheckCount])

  const applyAcceptedMergeProposal = useCallback(
    (proposal: CleanupAiProposal) => {
      const targetCanonicalId = proposal.target_canonical_id
      if (proposal.action !== "merge" || !targetCanonicalId) return
      setClusterResults((prev) => {
        if (!prev) return prev
        let next = prev
        for (const memberId of proposal.member_ids) {
          if (memberId === targetCanonicalId) continue
          next = applyMergeToClusterResults(next, memberId, targetCanonicalId, 0)
        }
        return next
      })
    },
    [],
  )

  const applyAcceptedKeepSeparateProposal = useCallback((proposal: CleanupAiProposal) => {
    if (proposal.action !== "keep_separate") return
    setClusterResults((prev) =>
      prev
        ? applyKeepSeparateProposalToClusterResults(
            prev,
            proposal,
            dismissedCleanupPairsRef.current,
          )
        : prev,
    )
  }, [])

  const handleAcceptAiProposal = useCallback(
    async (proposal: CleanupAiProposal) => {
      if (!stylebookSlug) return
      try {
        const result = await acceptCleanupAiProposal({
          stylebookSlug,
          proposalId: proposal.id,
        })
        if (result.status === "applied") {
          if (proposal.action === "merge") {
            applyAcceptedMergeProposal(proposal)
          } else if (proposal.action === "keep_separate") {
            applyAcceptedKeepSeparateProposal(proposal)
          }
          void refreshHubCheckCount()
        }
        removeAiProposal(proposal.id)
      } catch (error) {
        showError(error instanceof Error ? error.message : "Failed to accept AI suggestion")
      }
    },
    [
      stylebookSlug,
      showError,
      applyAcceptedMergeProposal,
      applyAcceptedKeepSeparateProposal,
      removeAiProposal,
      refreshHubCheckCount,
    ],
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
        if (result.status === "applied") {
          if (proposal.action === "merge") {
            applyAcceptedMergeProposal(proposal)
          } else if (proposal.action === "keep_separate") {
            applyAcceptedKeepSeparateProposal(proposal)
          }
        }
        removeAiProposal(proposal.id)
      } catch {
        // Continue with remaining proposals.
      }
    }
    void refreshHubCheckCount()
  }, [
    stylebookSlug,
    highConfidenceProposals,
    applyAcceptedMergeProposal,
    applyAcceptedKeepSeparateProposal,
    removeAiProposal,
    refreshHubCheckCount,
  ])

  const handleReviewStarted = useCallback(
    (reviewId: string) => {
      void startAiReviewTracking(reviewId)
    },
    [startAiReviewTracking],
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

  const showAiReviewControls =
    canEdit &&
    isClusterCheck &&
    checkRunStatus === "succeeded" &&
    (loading || pagination.total > 0 || aiReviewActive)

  const needsRun =
    checkRunStatus === "never_run" ||
    checkRunStatus === "queued" ||
    checkRunStatus === "running" ||
    checkRunStatus === "failed"

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
            { label: "Checks", to: cleanupHubPath },
            { label: config.title },
          ]}
          className="mb-3"
        />
        <h1 className="text-3xl font-bold">{config.title}</h1>
        <p className="text-muted-foreground mt-2">{config.description}</p>
      </div>

      <StylebookHomeTabs />

      {showAiReviewControls ? (
        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            variant={aiReviewActive ? "destructive" : "outline"}
            disabled={stoppingAiReview}
            onClick={() => void handleAiReviewButtonClick()}
          >
            {stoppingAiReview ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
                Stopping…
              </>
            ) : aiReviewActive ? (
              "Stop"
            ) : (
              <>
                <Sparkles className="h-4 w-4 mr-2" />
                Review with AI
              </>
            )}
          </Button>
          {aiReviewActive ? (
            <span className="text-sm text-muted-foreground inline-flex items-center gap-2">
              <Loader2 className="h-4 w-4 animate-spin" />
              Reviewing clusters ({aiReview?.processed_cluster_count ?? 0}/
              {aiReview?.cluster_count ?? 0})…
            </span>
          ) : null}
          {aiReview?.status === "cancelled" ? (
            <span className="text-sm text-muted-foreground">Review stopped</span>
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

      {showAiReviewControls ? (
        <CleanupAiReviewDialog
          open={aiDialogOpen}
          onOpenChange={setAiDialogOpen}
          stylebookSlug={stylebookSlug}
          checkId={config.id}
          onReviewStarted={handleReviewStarted}
        />
      ) : null}

      {isClusterCheck ? (
        <div className="max-w-md">
          <Input
            type="search"
            placeholder="Filter by name…"
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
            aria-label="Filter duplicate clusters by name"
          />
        </div>
      ) : null}

      {loading ? (
        <div className="flex items-center gap-2 text-muted-foreground py-8">
          <Loader2 className="h-5 w-5 animate-spin" />
          Loading…
        </div>
      ) : needsRun ? (
        <p className="text-muted-foreground py-8 text-center">
          {checkRunStatus === "running" || checkRunStatus === "queued"
            ? "This check is running. Results will appear here when it finishes."
            : checkRunStatus === "failed"
              ? "This check failed. Run it again from the Checks tab to see candidates."
              : "Run this check from the Checks tab to see candidates."}
        </p>
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
      ) : config.id === "missing-geometry-locations" ? (
        <GeographyIssuesList
          canonicals={(listResults as PaginatedCleanupLocationIssuesResponse | null)?.canonicals ?? []}
          locationDetailHref={detailHref}
          canEdit={canEdit}
          onDismiss={canEdit ? handleDismissListIssue : undefined}
        />
      ) : isQuestionableCanonicalCheck ? (
        <QuestionableCanonicalsList
          canonicals={questionableCanonicalResults?.canonicals ?? []}
          totalOpen={questionableCanonicalResults?.total ?? 0}
          entityType={entityType}
          detailHref={detailHref}
          canEdit={canEdit}
          bulkAction={questionableBulkAction}
          onKeep={canEdit ? handleKeepQuestionableCanonical : undefined}
          onDelete={canEdit ? handleDeleteQuestionableCanonical : undefined}
          onKeepAll={canEdit ? handleKeepAllQuestionableCanonicals : undefined}
          onDeleteAll={canEdit ? handleDeleteAllQuestionableCanonicals : undefined}
        />
      ) : (
        <MismatchedLinksList
          canonicals={(listResults as PaginatedCleanupMismatchIssuesResponse | null)?.canonicals ?? []}
          entityType={entityType}
          detailHref={detailHref}
          canEdit={canEdit}
          onDismiss={canEdit ? handleDismissListIssue : undefined}
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
          itemLabel={
            config.kind === "cluster"
              ? "clusters"
              : entityType === "location"
                ? "locations"
                : entityType === "person"
                  ? "people"
                  : "organizations"
          }
        />
      ) : null}
    </div>
  )
}

function mismatchExamplesLabel(examples: string[], count: number): string {
  const shown = examples.filter(Boolean)
  if (shown.length === 0) {
    return count === 1 ? "1 mismatched link" : `${count} mismatched links`
  }
  const suffix =
    count > shown.length ? ` (+${count - shown.length} more)` : ""
  return `${shown.join("; ")}${suffix}`
}

function MismatchedLinksList({
  canonicals,
  entityType,
  detailHref,
  canEdit = false,
  onDismiss,
}: {
  canonicals: CleanupMismatchIssue[]
  entityType: CleanupEntityType
  detailHref: (canonicalId: string) => string
  canEdit?: boolean
  onDismiss?: (canonicalId: string) => void | Promise<void>
}) {
  const emptyLabel =
    entityType === "person"
      ? "No people with potential mismatched links in this stylebook."
      : entityType === "organization"
        ? "No organizations with potential mismatched links in this stylebook."
        : "No places with potential mismatched links in this stylebook."

  if (canonicals.length === 0) {
    return <p className="text-muted-foreground py-8 text-center">{emptyLabel}</p>
  }

  const typeLabel = (canonical: CleanupMismatchIssue): string => {
    if (entityType === "person" && canonical.person_type) {
      return placeExtractTypeLabel(canonical.person_type)
    }
    if (entityType === "organization" && canonical.organization_type) {
      return placeExtractTypeLabel(canonical.organization_type)
    }
    if (entityType === "location" && canonical.location_type) {
      return placeExtractTypeLabel(canonical.location_type)
    }
    return "—"
  }

  return (
    <div className="rounded-lg border overflow-hidden">
      <table className="w-full table-fixed text-sm">
        <colgroup>
          {canEdit && onDismiss ? (
            <>
              <col style={{ width: "20%" }} />
              <col style={{ width: "24%" }} />
              <col style={{ width: "11%" }} />
              <col style={{ width: "9%" }} />
              <col style={{ width: "7%" }} />
              <col style={{ width: "7%" }} />
              <col style={{ width: "22%" }} />
            </>
          ) : (
            <>
              <col style={{ width: "26%" }} />
              <col style={{ width: "32%" }} />
              <col style={{ width: "12%" }} />
              <col style={{ width: "10%" }} />
              <col style={{ width: "10%" }} />
              <col style={{ width: "10%" }} />
            </>
          )}
        </colgroup>
        <thead className="bg-muted/50 text-left">
          <tr>
            <th className="px-3 py-3 font-medium min-w-0">Name</th>
            <th className="px-3 py-3 font-medium min-w-0">Example mismatched links</th>
            <th className="px-3 py-3 font-medium min-w-0">Type</th>
            <th className="px-3 py-3 font-medium min-w-0">Status</th>
            <th className="px-3 py-3 font-medium text-right">Linked</th>
            <th className="px-3 py-3 font-medium text-right">Mentions</th>
            {canEdit && onDismiss ? (
              <th className="px-3 py-3 font-medium text-right">Action</th>
            ) : null}
          </tr>
        </thead>
        <tbody>
          {canonicals.map((canonical) => {
            const examplesText = mismatchExamplesLabel(
              canonical.mismatched_examples ?? [],
              canonical.mismatched_linked_count ?? 0,
            )
            return (
              <tr key={canonical.id} className="border-t hover:bg-muted/30">
                <td className="px-3 py-3 min-w-0">
                  <Link
                    to={detailHref(canonical.id)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="font-medium text-primary hover:underline block truncate"
                    title={canonical.label}
                  >
                    {canonical.label}
                  </Link>
                </td>
                <td className="px-3 py-3 text-muted-foreground min-w-0">
                  <span className="block truncate" title={examplesText}>
                    {examplesText}
                  </span>
                </td>
                <td className="px-3 py-3 text-muted-foreground min-w-0">
                  <span className="block truncate">{typeLabel(canonical)}</span>
                </td>
                <td className="px-3 py-3 text-muted-foreground min-w-0">
                  <span className="block truncate">{canonical.status}</span>
                </td>
                <td className="px-3 py-3 text-right tabular-nums">
                  {canonical.linked_substrate_count ?? 0}
                </td>
                <td className="px-3 py-3 text-right tabular-nums">
                  {canonical.mention_count ?? 0}
                </td>
                {canEdit && onDismiss ? (
                  <td className="px-2 py-3 text-right whitespace-nowrap">
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
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function questionableCategoryLabel(category: string, entityType: CleanupEntityType): string {
  if (entityType === "person") {
    switch (category) {
      case "organization_like":
        return "Likely an organization"
      case "role_phrase":
        return "Likely an unnamed role"
      default:
        return "Likely not a person"
    }
  }
  switch (category) {
    case "person_like":
      return "Likely a person"
    case "place_like":
      return "Likely a place"
    case "law_policy_program":
      return "Likely a law or program"
    case "event_award_history":
      return "Likely an event or award"
    case "generic_group":
      return "Likely a broad group or descriptor"
    case "work_or_topic":
      return "Likely a film, publication, or topic"
    default:
      return "Likely not an organization"
  }
}

function questionableMentionPreview(mentions: string[]): string {
  const shown = mentions.filter(Boolean)
  if (shown.length === 0) {
    return "No sample mentions"
  }
  return shown.join("; ")
}

function QuestionableCanonicalsList({
  canonicals,
  totalOpen,
  entityType,
  detailHref,
  canEdit = false,
  bulkAction = null,
  onKeep,
  onDelete,
  onKeepAll,
  onDeleteAll,
}: {
  canonicals: CleanupQuestionableCanonicalIssue[]
  totalOpen: number
  entityType: CleanupEntityType
  detailHref: (canonicalId: string) => string
  canEdit?: boolean
  bulkAction?: "keep-all" | "delete-all" | null
  onKeep?: (canonicalId: string) => void | Promise<void>
  onDelete?: (canonicalId: string) => void | Promise<void>
  onKeepAll?: () => void | Promise<void>
  onDeleteAll?: () => void | Promise<void>
}) {
  const showActions = canEdit && onKeep && onDelete
  const showBulkActions = showActions && onKeepAll && onDeleteAll && totalOpen > 0
  const bulkBusy = bulkAction !== null
  const keepingAll = bulkAction === "keep-all"
  const deletingAll = bulkAction === "delete-all"

  if (canonicals.length === 0) {
    return (
      <p className="text-muted-foreground py-8 text-center">
        {entityType === "person"
          ? "No questionable person canonicals in this stylebook."
          : "No questionable organization canonicals in this stylebook."}
      </p>
    )
  }

  return (
    <div className="space-y-3">
      {showBulkActions ? (
        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={bulkBusy}
            onClick={() => void onKeepAll()}
          >
            {keepingAll ? (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
            ) : null}
            <span className={keepingAll ? "ml-1.5" : undefined}>
              {keepingAll ? "Keeping all…" : `Keep all (${totalOpen.toLocaleString()})`}
            </span>
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="text-destructive hover:text-destructive"
            disabled={bulkBusy}
            onClick={() => void onDeleteAll()}
          >
            {deletingAll ? (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
            ) : null}
            <span className={deletingAll ? "ml-1.5" : undefined}>
              {deletingAll ? "Deleting all…" : `Delete all (${totalOpen.toLocaleString()})`}
            </span>
          </Button>
        </div>
      ) : null}
      <div className="rounded-lg border overflow-hidden">
      <table className="w-full table-fixed text-sm">
        <colgroup>
          {showActions ? (
            <>
              <col style={{ width: "17%" }} />
              <col style={{ width: "13%" }} />
              <col style={{ width: "22%" }} />
              <col style={{ width: "17%" }} />
              <col style={{ width: "7%" }} />
              <col style={{ width: "7%" }} />
              <col style={{ width: "17%" }} />
            </>
          ) : (
            <>
              <col style={{ width: "20%" }} />
              <col style={{ width: "16%" }} />
              <col style={{ width: "28%" }} />
              <col style={{ width: "20%" }} />
              <col style={{ width: "8%" }} />
              <col style={{ width: "8%" }} />
            </>
          )}
        </colgroup>
        <thead className="bg-muted/50 text-left">
          <tr>
            <th className="px-3 py-3 font-medium min-w-0">Name</th>
            <th className="px-3 py-3 font-medium min-w-0">Issue</th>
            <th className="px-3 py-3 font-medium min-w-0">Why flagged</th>
            <th className="px-3 py-3 font-medium min-w-0">Sample mentions</th>
            <th className="px-3 py-3 font-medium text-right">Linked</th>
            <th className="px-3 py-3 font-medium text-right">Mentions</th>
            {showActions ? (
              <th className="px-3 py-3 font-medium text-right">Action</th>
            ) : null}
          </tr>
        </thead>
        <tbody>
          {canonicals.map((canonical) => {
            const mentionPreview = questionableMentionPreview(canonical.sample_mentions ?? [])
            const issueLabel = questionableCategoryLabel(canonical.category, entityType)
            return (
              <tr key={canonical.id} className="border-t hover:bg-muted/30">
                <td className="px-3 py-3 min-w-0">
                  <Link
                    to={detailHref(canonical.id)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="font-medium text-primary hover:underline block truncate"
                    title={canonical.label}
                  >
                    {canonical.label}
                  </Link>
                  <div className="text-xs text-muted-foreground truncate">
                    {entityType === "person" && canonical.person_type
                      ? placeExtractTypeLabel(canonical.person_type)
                      : entityType === "organization" && canonical.organization_type
                        ? placeExtractTypeLabel(canonical.organization_type)
                      : "—"}
                  </div>
                </td>
                <td className="px-3 py-3 text-muted-foreground min-w-0">
                  <span className="block truncate" title={issueLabel}>
                    {issueLabel}
                  </span>
                  <div className="text-xs truncate">
                    {canonical.confidence} confidence
                  </div>
                </td>
                <td className="px-3 py-3 text-muted-foreground min-w-0">
                  <span className="block truncate" title={canonical.explanation}>
                    {canonical.explanation}
                  </span>
                </td>
                <td className="px-3 py-3 text-muted-foreground min-w-0">
                  <span className="block truncate" title={mentionPreview}>
                    {mentionPreview}
                  </span>
                </td>
                <td className="px-3 py-3 text-right tabular-nums">
                  {canonical.linked_substrate_count ?? 0}
                </td>
                <td className="px-3 py-3 text-right tabular-nums">
                  {canonical.mention_count ?? 0}
                </td>
                {showActions ? (
                  <td className="px-2 py-3 text-right whitespace-nowrap">
                    <div className="inline-flex items-center justify-end gap-1.5">
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        disabled={bulkBusy}
                        onClick={() => void onKeep(canonical.id)}
                      >
                        Keep
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="text-destructive hover:text-destructive"
                        disabled={bulkBusy}
                        onClick={() => void onDelete(canonical.id)}
                      >
                        Delete
                      </Button>
                    </div>
                  </td>
                ) : null}
              </tr>
            )
          })}
        </tbody>
      </table>
      </div>
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
        No locations with potential missing or incorrect geographies in this stylebook.
      </p>
    )
  }

  return (
    <div className="rounded-lg border overflow-hidden">
      <table className="w-full table-fixed text-sm">
        <colgroup>
          {canEdit && onDismiss ? (
            <>
              <col style={{ width: "22%" }} />
              <col style={{ width: "22%" }} />
              <col style={{ width: "11%" }} />
              <col style={{ width: "9%" }} />
              <col style={{ width: "7%" }} />
              <col style={{ width: "7%" }} />
              <col style={{ width: "22%" }} />
            </>
          ) : (
            <>
              <col style={{ width: "28%" }} />
              <col style={{ width: "28%" }} />
              <col style={{ width: "12%" }} />
              <col style={{ width: "10%" }} />
              <col style={{ width: "11%" }} />
              <col style={{ width: "11%" }} />
            </>
          )}
        </colgroup>
        <thead className="bg-muted/50 text-left">
          <tr>
            <th className="px-3 py-3 font-medium min-w-0">Name</th>
            <th className="px-3 py-3 font-medium min-w-0">Issue</th>
            <th className="px-3 py-3 font-medium min-w-0">Type</th>
            <th className="px-3 py-3 font-medium min-w-0">Status</th>
            <th className="px-3 py-3 font-medium text-right">Linked</th>
            <th className="px-3 py-3 font-medium text-right">Mentions</th>
            {canEdit && onDismiss ? (
              <th className="px-3 py-3 font-medium text-right">Action</th>
            ) : null}
          </tr>
        </thead>
        <tbody>
          {canonicals.map((canonical) => (
            <tr key={canonical.id} className="border-t hover:bg-muted/30">
              <td className="px-3 py-3 min-w-0">
                <Link
                  to={locationDetailHref(canonical.id)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-medium text-primary hover:underline block truncate"
                  title={canonical.label}
                >
                  {canonical.label}
                </Link>
              </td>
              <td className="px-3 py-3 text-muted-foreground min-w-0">
                <span
                  className="block truncate"
                  title={geographyIssueLabel(canonical.geography_issue)}
                >
                  {geographyIssueLabel(canonical.geography_issue)}
                  {canonical.geography_issue === "distant_linked_places" &&
                  (canonical.distant_linked_count ?? 0) > 0
                    ? ` (${canonical.distant_linked_count})`
                    : null}
                </span>
              </td>
              <td className="px-3 py-3 text-muted-foreground min-w-0">
                <span className="block truncate">
                  {canonical.location_type
                    ? placeExtractTypeLabel(canonical.location_type)
                    : "—"}
                </span>
              </td>
              <td className="px-3 py-3 text-muted-foreground min-w-0">
                <span className="block truncate">{canonical.status}</span>
              </td>
              <td className="px-3 py-3 text-right tabular-nums">
                {canonical.linked_substrate_count ?? 0}
              </td>
              <td className="px-3 py-3 text-right tabular-nums">
                {canonical.mention_count ?? 0}
              </td>
              {canEdit && onDismiss ? (
                <td className="px-2 py-3 text-right whitespace-nowrap">
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
