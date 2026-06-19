import type { CleanupAiProposal, DuplicateCluster } from "@/lib/stylebook-api/cleanup"

export const CLEANUP_AI_HIGH_CONFIDENCE_THRESHOLD = 0.9

export function clusterMemberIds(cluster: DuplicateCluster): Set<string> {
  return new Set(cluster.canonicals.map((canonical) => canonical.id))
}

export function proposalBelongsToCluster(
  proposal: CleanupAiProposal,
  cluster: DuplicateCluster,
): boolean {
  const memberIds = clusterMemberIds(cluster)
  return proposal.member_ids.every((memberId) => memberIds.has(memberId))
}

export function proposalsForCluster(
  proposals: CleanupAiProposal[],
  cluster: DuplicateCluster,
): CleanupAiProposal[] {
  return proposals.filter((proposal) => proposalBelongsToCluster(proposal, cluster))
}

export function isTerminalReviewStatus(status: string): boolean {
  return status === "succeeded" || status === "failed" || status === "cancelled"
}

export function isActiveReviewStatus(status: string): boolean {
  return status === "queued" || status === "running"
}
