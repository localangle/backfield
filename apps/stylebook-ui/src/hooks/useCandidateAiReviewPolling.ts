import { useCallback, useEffect, useRef, useState } from "react"
import {
  cancelCandidateAiReview,
  getCandidateAiReview,
  getLatestCandidateAiReview,
  type CandidateAiReview,
  type CandidateAiReviewEntityType,
} from "@/lib/api"
import { isActiveReviewStatus, isTerminalReviewStatus } from "@/lib/cleanupAiReview"

const POLL_INTERVAL_MS = 1500

export function useCandidateAiReviewPolling(params: {
  stylebookSlug: string
  projectSlug: string
  entityType: CandidateAiReviewEntityType
  enabled: boolean
  onReviewTerminal?: () => void
  onProgress?: (processed: number, total: number) => void
}) {
  const { stylebookSlug, projectSlug, entityType, enabled, onReviewTerminal, onProgress } = params
  const [review, setReview] = useState<CandidateAiReview | null>(null)
  const [loading, setLoading] = useState(false)
  const onTerminalRef = useRef(onReviewTerminal)
  const onProgressRef = useRef(onProgress)
  const lastProcessedRef = useRef(0)
  onTerminalRef.current = onReviewTerminal
  onProgressRef.current = onProgress

  const applyReviewUpdate = useCallback((next: CandidateAiReview) => {
    setReview(next)
    if (next.processed_count > lastProcessedRef.current) {
      lastProcessedRef.current = next.processed_count
      onProgressRef.current?.(next.processed_count, next.candidate_count)
    }
    if (isTerminalReviewStatus(next.status)) {
      onTerminalRef.current?.()
    }
  }, [])

  const refreshReview = useCallback(
    async (reviewId: string) => {
      const next = await getCandidateAiReview(stylebookSlug, reviewId)
      applyReviewUpdate(next)
      return next
    },
    [stylebookSlug, applyReviewUpdate],
  )

  const startTracking = useCallback(
    async (reviewId: string) => {
      lastProcessedRef.current = 0
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
    const next = await cancelCandidateAiReview(stylebookSlug, review.id)
    applyReviewUpdate(next)
    return next
  }, [review, stylebookSlug, applyReviewUpdate])

  useEffect(() => {
    if (!enabled || !stylebookSlug || !projectSlug || !entityType) return
    let cancelled = false
    void (async () => {
      setLoading(true)
      try {
        const latest = await getLatestCandidateAiReview(stylebookSlug, entityType, projectSlug)
        if (cancelled || !latest) return
        lastProcessedRef.current = latest.processed_count
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
    stopReview,
  }
}
