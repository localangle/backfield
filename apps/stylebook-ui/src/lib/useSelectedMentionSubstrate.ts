import { useEffect, useState } from "react"

/**
 * Selected-substrate state for canonical detail mentions in "selectable" mode.
 *
 * Auto-selects the first linked substrate, clears when none remain (e.g. after
 * unlink), and falls back to the first substrate if the selected one
 * disappears. `resetKey` feeds `usePaginatedCanonicalMentions` so pagination
 * restarts when the substrate scope changes.
 */
export function useSelectedMentionSubstrate(substrates: ReadonlyArray<{ id: number }>) {
  const [selectedSubstrateId, setSelectedSubstrateId] = useState<number | null>(null)

  useEffect(() => {
    if (substrates.length === 0) {
      setSelectedSubstrateId(null)
      return
    }
    setSelectedSubstrateId((current) =>
      current != null && substrates.some((substrate) => substrate.id === current)
        ? current
        : substrates[0].id,
    )
  }, [substrates])

  return {
    selectedSubstrateId,
    setSelectedSubstrateId,
    resetKey: selectedSubstrateId == null ? "" : String(selectedSubstrateId),
  }
}
