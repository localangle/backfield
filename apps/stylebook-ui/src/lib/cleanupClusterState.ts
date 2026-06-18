import type {
  CleanupClusterCanonical,
  DuplicateCluster,
  PaginatedCleanupLocationIssuesResponse,
  PaginatedDuplicateClustersResponse,
} from "@/lib/stylebook-api/cleanup"

export function assignStableClusterIds(
  clusters: DuplicateCluster[],
  stableIdByMember: Map<string, string>,
  nextIdRef: { current: number },
): DuplicateCluster[] {
  return clusters.map((cluster) => {
    const stableFromMember = cluster.canonicals
      .map((canonical) => stableIdByMember.get(canonical.id))
      .find((id): id is string => Boolean(id))
    const stableId = stableFromMember ?? `cluster-local-${++nextIdRef.current}`
    for (const canonical of cluster.canonicals) {
      stableIdByMember.set(canonical.id, stableId)
    }
    return { ...cluster, cluster_id: stableId }
  })
}

function shrinkCluster(
  cluster: DuplicateCluster,
  nextCanonicals: CleanupClusterCanonical[],
): DuplicateCluster | null {
  if (nextCanonicals.length < 2) return null
  return { ...cluster, canonicals: nextCanonicals }
}

export function applyDeleteEmptyToClusterResults(
  results: PaginatedDuplicateClustersResponse,
  canonicalId: string,
): PaginatedDuplicateClustersResponse {
  const clusters: DuplicateCluster[] = []
  let clusterRemoved = false

  for (const cluster of results.clusters) {
    if (!cluster.canonicals.some((canonical) => canonical.id === canonicalId)) {
      clusters.push(cluster)
      continue
    }
    const next = shrinkCluster(
      cluster,
      cluster.canonicals.filter((canonical) => canonical.id !== canonicalId),
    )
    if (next) {
      clusters.push(next)
    } else {
      clusterRemoved = true
    }
  }

  return {
    ...results,
    clusters,
    total: clusterRemoved ? Math.max(0, results.total - 1) : results.total,
  }
}

export function applyMergeToClusterResults(
  results: PaginatedDuplicateClustersResponse,
  sourceId: string,
  targetId: string,
  relinkedSubstrateCount: number,
): PaginatedDuplicateClustersResponse {
  const clusters: DuplicateCluster[] = []
  let clusterRemoved = false

  for (const cluster of results.clusters) {
    if (!cluster.canonicals.some((canonical) => canonical.id === sourceId)) {
      clusters.push(cluster)
      continue
    }

    const nextCanonicals = cluster.canonicals
      .filter((canonical) => canonical.id !== sourceId)
      .map((canonical) =>
        canonical.id === targetId
          ? {
              ...canonical,
              linked_substrate_count:
                (canonical.linked_substrate_count ?? 0) + relinkedSubstrateCount,
            }
          : canonical,
      )

    const next = shrinkCluster(cluster, nextCanonicals)
    if (next) {
      clusters.push(next)
    } else {
      clusterRemoved = true
    }
  }

  return {
    ...results,
    clusters,
    total: clusterRemoved ? Math.max(0, results.total - 1) : results.total,
  }
}

export function applyDismissClusterToResults(
  results: PaginatedDuplicateClustersResponse,
  clusterId: string,
): PaginatedDuplicateClustersResponse {
  const clusters = results.clusters.filter((cluster) => cluster.cluster_id !== clusterId)
  const removed = clusters.length < results.clusters.length
  return {
    ...results,
    clusters,
    total: removed ? Math.max(0, results.total - 1) : results.total,
  }
}

export function applyDismissCanonicalToListResults(
  results: PaginatedCleanupLocationIssuesResponse,
  canonicalId: string,
): PaginatedCleanupLocationIssuesResponse {
  const canonicals = results.canonicals.filter((canonical) => canonical.id !== canonicalId)
  const removed = canonicals.length < results.canonicals.length
  return {
    ...results,
    canonicals,
    total: removed ? Math.max(0, results.total - 1) : results.total,
  }
}
