import { useCallback, useEffect, useState } from "react"
import type { LinkPickTableRow } from "@/components/LinkPickTable"
import { rankCandidatesByLabelSimilarity } from "@/lib/candidateQueueSimilarity"
import {
  type CandidateQueueLinkedToast,
  type CandidateQueueToastCanonical,
  useAutoDismissToast,
} from "@/lib/candidateQueueToast"

const TOAST_FOLLOWUP_PREFETCH_LIMIT = 100
const TOAST_FOLLOWUP_RANK_TOP = 5

export type UseCandidateQueueToastsOptions<TCandidate extends { id: number }> = {
  projectSlug: string | undefined
  /** Open-queue search used after creating a canonical (same `q=` as the new label). */
  fetchOpenCandidatesForLabel: (label: string) => Promise<TCandidate[]>
  getCandidateLabel: (row: TCandidate) => string
  mapFollowupRow: (row: TCandidate) => LinkPickTableRow
  linkCandidateToCanonical: (row: TCandidate, canonicalId: string) => Promise<void>
  onAfterToastLink?: () => void | Promise<void>
}

export function useCandidateQueueToasts<TCandidate extends { id: number }>({
  projectSlug,
  fetchOpenCandidatesForLabel,
  getCandidateLabel,
  mapFollowupRow,
  linkCandidateToCanonical,
  onAfterToastLink,
}: UseCandidateQueueToastsOptions<TCandidate>) {
  const created = useAutoDismissToast<CandidateQueueToastCanonical>()
  const linked = useAutoDismissToast<CandidateQueueLinkedToast>()

  const [toastLinkTarget, setToastLinkTarget] = useState<CandidateQueueToastCanonical | null>(
    null,
  )
  const [toastFollowupLoading, setToastFollowupLoading] = useState(false)
  const [toastFollowupError, setToastFollowupError] = useState<string | null>(null)
  const [toastFollowupRows, setToastFollowupRows] = useState<TCandidate[]>([])
  const [potentialLinksOpen, setPotentialLinksOpen] = useState(false)
  const [toastLinkBusyId, setToastLinkBusyId] = useState<number | null>(null)
  const [toastLinkError, setToastLinkError] = useState<string | null>(null)

  const clearFollowupState = useCallback(() => {
    setToastFollowupRows([])
    setToastFollowupLoading(false)
    setToastFollowupError(null)
    setToastLinkBusyId(null)
    setToastLinkError(null)
    setToastLinkTarget(null)
  }, [])

  const prefetchToastFollowupCandidates = useCallback(async () => {
    const label = toastLinkTarget?.canonicalLabel?.trim()
    if (!projectSlug || !label) return
    setToastFollowupLoading(true)
    setToastFollowupError(null)
    try {
      const rows = await fetchOpenCandidatesForLabel(label)
      const ranked = rankCandidatesByLabelSimilarity(rows, label, getCandidateLabel).slice(
        0,
        TOAST_FOLLOWUP_RANK_TOP,
      )
      setToastFollowupRows(ranked)
    } catch (e) {
      setToastFollowupError(e instanceof Error ? e.message : "Couldn't load candidates")
      setToastFollowupRows([])
    } finally {
      setToastFollowupLoading(false)
    }
  }, [projectSlug, toastLinkTarget?.canonicalLabel, fetchOpenCandidatesForLabel, getCandidateLabel])

  useEffect(() => {
    if (!toastLinkTarget || !projectSlug) {
      if (!potentialLinksOpen) {
        setToastFollowupRows([])
        setToastFollowupLoading(false)
        setToastFollowupError(null)
        setToastLinkBusyId(null)
        setToastLinkError(null)
      }
      return
    }
    void prefetchToastFollowupCandidates()
  }, [toastLinkTarget, projectSlug, potentialLinksOpen, prefetchToastFollowupCandidates])

  const showCreated = useCallback(
    (target: CandidateQueueToastCanonical) => {
      setToastLinkTarget(target)
      created.show(target)
    },
    [created],
  )

  const dismissCreatedNow = useCallback(() => {
    created.dismissNow()
    if (!potentialLinksOpen) {
      setToastFollowupRows([])
      setToastFollowupLoading(false)
      setToastFollowupError(null)
      setToastLinkTarget(null)
    }
  }, [created, potentialLinksOpen])

  const onPotentialLinksOpenChange = useCallback(
    (open: boolean) => {
      setPotentialLinksOpen(open)
      if (!open) {
        setToastLinkError(null)
        setToastLinkBusyId(null)
        clearFollowupState()
      }
    },
    [clearFollowupState],
  )

  const linkToastCandidate = useCallback(
    async (row: TCandidate) => {
      if (!projectSlug || !toastLinkTarget) return
      setToastLinkError(null)
      setToastLinkBusyId(row.id)
      try {
        await linkCandidateToCanonical(row, toastLinkTarget.canonicalId)
        setToastFollowupRows((rows) => rows.filter((r) => r.id !== row.id))
        await onAfterToastLink?.()
      } catch (e) {
        setToastLinkError(e instanceof Error ? e.message : "Link failed")
      } finally {
        setToastLinkBusyId(null)
      }
    },
    [projectSlug, toastLinkTarget, linkCandidateToCanonical, onAfterToastLink],
  )

  const potentialLinksDialog = {
    open: potentialLinksOpen,
    onOpenChange: onPotentialLinksOpenChange,
    canonicalLabel: toastLinkTarget?.canonicalLabel ?? "",
    loading: toastFollowupLoading,
    error: toastLinkError ?? toastFollowupError,
    rows: toastFollowupRows.map(mapFollowupRow),
    busyKey: toastLinkBusyId,
    linkDisabled: !toastLinkTarget,
    onLink: (rowKey: string | number) => {
      const row = toastFollowupRows.find((r) => r.id === rowKey)
      if (row) void linkToastCandidate(row)
    },
    onRefresh: () => void prefetchToastFollowupCandidates(),
  }

  return {
    created: {
      payload: created.payload,
      leaving: created.leaving,
      isVisible: created.isVisible,
      show: showCreated,
      dismissNow: dismissCreatedNow,
    },
    linked: {
      payload: linked.payload,
      leaving: linked.leaving,
      isVisible: linked.isVisible,
      show: linked.show,
      dismissNow: linked.dismissNow,
    },
    followup: {
      loading: toastFollowupLoading,
      error: toastFollowupError,
      hasMatches: !toastFollowupLoading && toastFollowupRows.length > 0,
      openPotentialLinks: () => setPotentialLinksOpen(true),
    },
    potentialLinksDialog,
  }
}
