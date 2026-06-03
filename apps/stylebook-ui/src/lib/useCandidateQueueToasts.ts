import { useCallback, useRef, useState } from "react"
import type { LinkPickTableRow } from "@/components/LinkPickTable"
import { rankCandidatesByLabelSimilarity } from "@/lib/candidateQueueSimilarity"
import {
  type CandidateQueueLinkedToast,
  type CandidateQueueToastCanonical,
  useAutoDismissToast,
} from "@/lib/candidateQueueToast"

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

  const fetchOpenCandidatesRef = useRef(fetchOpenCandidatesForLabel)
  const getCandidateLabelRef = useRef(getCandidateLabel)
  const linkCandidateToCanonicalRef = useRef(linkCandidateToCanonical)
  const onAfterToastLinkRef = useRef(onAfterToastLink)
  const toastLinkTargetRef = useRef<CandidateQueueToastCanonical | null>(null)
  const followupPrefetchKeyRef = useRef<string | null>(null)
  const followupPrefetchInFlightRef = useRef<string | null>(null)
  const potentialLinksOpenRef = useRef(false)

  fetchOpenCandidatesRef.current = fetchOpenCandidatesForLabel
  getCandidateLabelRef.current = getCandidateLabel
  linkCandidateToCanonicalRef.current = linkCandidateToCanonical
  onAfterToastLinkRef.current = onAfterToastLink
  toastLinkTargetRef.current = toastLinkTarget
  potentialLinksOpenRef.current = potentialLinksOpen

  const clearFollowupState = useCallback(() => {
    followupPrefetchKeyRef.current = null
    followupPrefetchInFlightRef.current = null
    toastLinkTargetRef.current = null
    setToastFollowupRows([])
    setToastFollowupLoading(false)
    setToastFollowupError(null)
    setToastLinkBusyId(null)
    setToastLinkError(null)
    setToastLinkTarget(null)
  }, [])

  const runFollowupPrefetch = useCallback(
    async (target: CandidateQueueToastCanonical, force = false) => {
      const label = target.canonicalLabel.trim()
      const canonicalId = target.canonicalId.trim()
      if (!projectSlug || !label || !canonicalId) return

      const prefetchKey = `${projectSlug}|${canonicalId}|${label}`
      if (
        !force &&
        (followupPrefetchKeyRef.current === prefetchKey ||
          followupPrefetchInFlightRef.current === prefetchKey)
      ) {
        return
      }

      followupPrefetchInFlightRef.current = prefetchKey
      setToastFollowupLoading(true)
      setToastFollowupError(null)
      try {
        const rows = await fetchOpenCandidatesRef.current(label)
        const ranked = rankCandidatesByLabelSimilarity(rows, label, (row) =>
          getCandidateLabelRef.current(row),
        ).slice(0, TOAST_FOLLOWUP_RANK_TOP)
        followupPrefetchKeyRef.current = prefetchKey
        setToastFollowupRows(ranked)
      } catch (e) {
        setToastFollowupError(e instanceof Error ? e.message : "Couldn't load candidates")
        setToastFollowupRows([])
      } finally {
        if (followupPrefetchInFlightRef.current === prefetchKey) {
          followupPrefetchInFlightRef.current = null
        }
        setToastFollowupLoading(false)
      }
    },
    [projectSlug],
  )

  const showCreated = useCallback(
    (target: CandidateQueueToastCanonical) => {
      toastLinkTargetRef.current = target
      setToastLinkTarget(target)
      created.show(target)
      void runFollowupPrefetch(target)
    },
    [created.show, runFollowupPrefetch],
  )

  const dismissCreatedNow = useCallback(() => {
    created.dismissNow()
    if (!potentialLinksOpen) {
      clearFollowupState()
    }
  }, [created.dismissNow, potentialLinksOpen, clearFollowupState])

  const onPotentialLinksOpenChange = useCallback(
    (open: boolean) => {
      if (open) {
        setPotentialLinksOpen(true)
        return
      }
      // Radix may emit `false` while already closed; ignore so we do not wipe follow-up state.
      if (!potentialLinksOpenRef.current) return
      setPotentialLinksOpen(false)
      setToastLinkError(null)
      setToastLinkBusyId(null)
      clearFollowupState()
    },
    [clearFollowupState],
  )

  const linkToastCandidate = useCallback(async (row: TCandidate) => {
    const target = toastLinkTargetRef.current
    if (!projectSlug || !target) return
    setToastLinkError(null)
    setToastLinkBusyId(row.id)
    try {
      await linkCandidateToCanonicalRef.current(row, target.canonicalId)
      setToastFollowupRows((rows) => rows.filter((r) => r.id !== row.id))
      await onAfterToastLinkRef.current?.()
    } catch (e) {
      setToastLinkError(e instanceof Error ? e.message : "Link failed")
    } finally {
      setToastLinkBusyId(null)
    }
  }, [projectSlug])

  const onFollowupRefresh = useCallback(() => {
    const target = toastLinkTargetRef.current
    if (!target) return
    void runFollowupPrefetch(target, true)
  }, [runFollowupPrefetch])

  const onFollowupLink = useCallback(
    (rowKey: string | number) => {
      const row = toastFollowupRows.find((r) => r.id === rowKey)
      if (row) void linkToastCandidate(row)
    },
    [toastFollowupRows, linkToastCandidate],
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
    onLink: onFollowupLink,
    onRefresh: onFollowupRefresh,
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
