import { useCallback, useEffect, useState } from "react"

/** Shared timing for Stylebook candidate success toasts. */
export const CANDIDATE_TOAST_AUTO_DISMISS_MS = 3000
export const CANDIDATE_TOAST_FADE_MS = 300

export type CandidateQueueToastCanonical = {
  canonicalLabel: string
  canonicalId: string
}

export type CandidateQueueLinkedToast = CandidateQueueToastCanonical & {
  candidateLabel: string
}

/** Auto-dismiss toast with fade-out; manual dismiss clears immediately. */
export function useAutoDismissToast<T>() {
  const [payload, setPayload] = useState<T | null>(null)
  const [leaving, setLeaving] = useState(false)

  const show = useCallback((next: T) => {
    setLeaving(false)
    setPayload(next)
  }, [])

  const dismissNow = useCallback(() => {
    setLeaving(false)
    setPayload(null)
  }, [])

  useEffect(() => {
    if (!payload) {
      setLeaving(false)
      return
    }
    setLeaving(false)
    const timeouts = { main: 0 as number, fade: undefined as number | undefined }
    timeouts.main = window.setTimeout(() => {
      setLeaving(true)
      timeouts.fade = window.setTimeout(() => {
        setPayload(null)
        setLeaving(false)
      }, CANDIDATE_TOAST_FADE_MS)
    }, CANDIDATE_TOAST_AUTO_DISMISS_MS)
    return () => {
      window.clearTimeout(timeouts.main)
      if (timeouts.fade !== undefined) window.clearTimeout(timeouts.fade)
    }
  }, [payload])

  return {
    payload,
    leaving,
    isVisible: payload !== null,
    show,
    dismissNow,
  }
}
