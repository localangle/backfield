import { useEffect, useRef } from "react"
import type { ShowAppConfirmOptions } from "@/components/AppMessageProvider"

export type UsePromptDeleteEmptyCanonicalOptions = {
  /** Changes reset mention/substrate baselines (e.g. stylebook + project + canonical id). */
  canonicalKey: string
  enabled?: boolean
  mentions: unknown[]
  mentionsLoading: boolean
  substrates: unknown[]
  substratesLoading: boolean
  showConfirm: (description: string, options?: ShowAppConfirmOptions) => Promise<boolean>
  onDelete: () => void | Promise<void>
}

/** After the last linked substrate is removed and nothing remains, offer to delete the canonical. */
export function usePromptDeleteEmptyCanonical({
  canonicalKey,
  enabled = true,
  mentions,
  mentionsLoading,
  substrates,
  substratesLoading,
  showConfirm,
  onDelete,
}: UsePromptDeleteEmptyCanonicalOptions): void {
  const prevMentionCountRef = useRef<number | null>(null)
  const prevSubstrateCountRef = useRef<number | null>(null)
  const lastCanonicalKeyRef = useRef<string>("")

  useEffect(() => {
    if (canonicalKey !== lastCanonicalKeyRef.current) {
      lastCanonicalKeyRef.current = canonicalKey
      prevMentionCountRef.current = null
      prevSubstrateCountRef.current = null
    }
  }, [canonicalKey])

  useEffect(() => {
    if (!enabled || !canonicalKey) return
    if (mentionsLoading || substratesLoading) return

    const mentionCount = mentions.length
    const substrateCount = substrates.length

    const prevMentions = prevMentionCountRef.current
    const prevSubs = prevSubstrateCountRef.current

    // Establish baseline after first successful refresh for this canonical.
    if (prevMentions === null || prevSubs === null) {
      prevMentionCountRef.current = mentionCount
      prevSubstrateCountRef.current = substrateCount
      return
    }

    const substratesCleared = prevSubs > 0 && substrateCount === 0
    const mentionsCleared = prevMentions > 0 && mentionCount === 0
    const fullyEmpty = substrateCount === 0 && mentionCount === 0

    if (fullyEmpty && (substratesCleared || mentionsCleared)) {
      void (async () => {
        const ok = await showConfirm(
          "All mentions for this canonical have been removed. Would you like to delete it?",
          {
            title: "Delete canonical?",
            confirmLabel: "Delete canonical",
            cancelLabel: "Keep",
            destructive: true,
          },
        )
        if (ok) {
          await onDelete()
        }
        prevMentionCountRef.current = mentionCount
        prevSubstrateCountRef.current = substrateCount
      })()
      return
    }

    prevMentionCountRef.current = mentionCount
    prevSubstrateCountRef.current = substrateCount
  }, [
    canonicalKey,
    enabled,
    mentions,
    mentionsLoading,
    substrates,
    substratesLoading,
    showConfirm,
    onDelete,
  ])
}
