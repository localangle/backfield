import { useCallback, useEffect, useRef, useState } from "react"
import {
  getCandidateAiReview,
  getLatestCandidateAiReview,
  type CandidateAiReview,
  type CandidateAiReviewEntityType,
} from "@/lib/api"
import { isTerminalReviewStatus } from "@/lib/cleanupAiReview"

const POLL_INTERVAL_MS = 2000

export function useCandidateAiReviewPolling(params: {
  stylebookSlug: string
  projectSlug: string
  entityType: CandidateAiReviewEntityType
  enabled: boolean
  onReviewTerminal?: () => void
}) {
  const { stylebookSlug, projectSlug, entityType, enabled, onReviewTerminal } = params
  const [review, setReview] = useState<CandidateAiReview | null>(null)
  const [loading, setLoading] = useState(false)
  const onTerminalRef = useRef(onReviewTerminal)
  onTerminalRef.current = onReviewTerminal

  const refreshReview = useCallback(
    async (reviewId: string) => {
      const next = await getCandidateAiReview(stylebookSlug, reviewId)
      setReview(next)
      if (isTerminalReviewStatus(next.status)) {
        onTerminalRef.current?.()
      }
      return next
    },
    [stylebookSlug],
  )

  const startTracking = useCallback(
    async (reviewId: string) => {
      setLoading(true)
      try {
        await refreshReview(reviewId)
      } finally {
        setLoading(false)
      }
    },
    [refreshReview],
  )

  useEffect(() => {
    if (!enabled || !stylebookSlug || !projectSlug || !entityType) return
    let cancelled = false
    void (async () => {
      setLoading(true)
      try {
        const latest = await getLatestCandidateAiReview(stylebookSlug, entityType, projectSlug)
        if (cancelled || !latest) return
        setReview(latest)
        if (isTerminalReviewStatus(latest.status)) {
          onTerminalRef.current?.()
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [enabled, stylebookSlug, projectSlug, entityType])

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
    loading,
    startTracking,
    refreshReview,
  }
}
