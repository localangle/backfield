import { useCallback, useEffect, useRef, useState } from "react"
import {
  cancelCleanupAiReview,
  getCleanupAiReview,
  getLatestCleanupAiReview,
  listCleanupAiProposals,
  type CleanupAiProposal,
  type CleanupAiReview,
} from "@/lib/api"
import { isActiveReviewStatus, isTerminalReviewStatus } from "@/lib/cleanupAiReview"

const POLL_INTERVAL_MS = 2000

export function useCleanupAiReviewPolling(params: {
  stylebookSlug: string
  checkId: string
  enabled: boolean
}) {
  const { stylebookSlug, checkId, enabled } = params
  const [review, setReview] = useState<CleanupAiReview | null>(null)
  const [proposals, setProposals] = useState<CleanupAiProposal[]>([])
  const [loading, setLoading] = useState(false)
  const activeReviewIdRef = useRef<string | null>(null)

  const loadProposals = useCallback(
    async (reviewId: string) => {
      const response = await listCleanupAiProposals({
        stylebookSlug,
        reviewId,
        status: "pending",
      })
      setProposals(response.proposals)
    },
    [stylebookSlug],
  )

  const refreshReview = useCallback(
    async (reviewId: string) => {
      const next = await getCleanupAiReview(stylebookSlug, reviewId)
      setReview(next)
      if (isTerminalReviewStatus(next.status)) {
        await loadProposals(reviewId)
      } else if (next.proposal_count > 0) {
        await loadProposals(reviewId)
      }
      return next
    },
    [stylebookSlug, loadProposals],
  )

  const startTracking = useCallback(
    async (reviewId: string) => {
      activeReviewIdRef.current = reviewId
      setLoading(true)
      try {
        await refreshReview(reviewId)
      } finally {
        setLoading(false)
      }
    },
    [refreshReview],
  )

  const stopReview = useCallback(async () => {
    if (!review || !isActiveReviewStatus(review.status)) return null
    const next = await cancelCleanupAiReview(stylebookSlug, review.id)
    setReview(next)
    return next
  }, [review, stylebookSlug])

  const removeProposal = useCallback((proposalId: string) => {
    setProposals((prev) => prev.filter((proposal) => proposal.id !== proposalId))
  }, [])

  useEffect(() => {
    if (!enabled || !stylebookSlug || !checkId) return
    let cancelled = false
    void (async () => {
      setLoading(true)
      try {
        const latest = await getLatestCleanupAiReview(stylebookSlug, checkId)
        if (cancelled || !latest) return
        activeReviewIdRef.current = latest.id
        setReview(latest)
        if (isTerminalReviewStatus(latest.status)) {
          await loadProposals(latest.id)
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [enabled, stylebookSlug, checkId, loadProposals])

  useEffect(() => {
    if (!review || isTerminalReviewStatus(review.status)) return
    const reviewId = review.id
    const timer = window.setInterval(() => {
      void refreshReview(reviewId)
    }, POLL_INTERVAL_MS)
    return () => window.clearInterval(timer)
  }, [review, refreshReview])

  return {
    review,
    proposals,
    loading,
    startTracking,
    refreshReview,
    stopReview,
    removeProposal,
    setProposals,
  }
}
