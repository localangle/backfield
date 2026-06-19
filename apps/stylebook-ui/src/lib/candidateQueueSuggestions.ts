import type {
  CandidateQueueSuggestionLabels,
  QueueCandidateBase,
} from "@/lib/entityConfigs/candidateQueueTypes"

export type SuggestedRowAction = "link" | "create_new" | "defer" | null

/** Row action aligned with `canonical_suggestion.suggested_action` from the API. */
export function suggestedRowAction(candidate: {
  canonical_suggestion?: { suggested_action?: string | null } | null
}): SuggestedRowAction {
  const raw = candidate.canonical_suggestion?.suggested_action
  if (raw === "link_existing") return "link"
  if (raw === "materialize_new") return "create_new"
  if (raw === "defer") return "defer"
  return null
}

export function suggestedActionShortLabel(
  candidate: { canonical_suggestion?: { suggested_action?: string | null } | null },
  labels: CandidateQueueSuggestionLabels,
): string | null {
  const sug = suggestedRowAction(candidate)
  if (sug === "link") return labels.link
  if (sug === "create_new") return labels.create_new
  if (sug === "defer") return labels.defer
  return null
}

export function candidatesWithSuggestedAction<T extends QueueCandidateBase>(
  candidates: T[],
): T[] {
  return candidates.filter((candidate) => suggestedRowAction(candidate) !== null)
}
