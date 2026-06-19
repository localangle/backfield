import { useState } from "react"
import { GripVertical, Sparkles, Trash2 } from "lucide-react"
import { Link } from "react-router-dom"
import type { CleanupAiProposal, CleanupClusterCanonical } from "@/lib/api"
import type { CleanupEntityType } from "@/lib/cleanupChecks"
import { proposalsForCluster } from "@/lib/cleanupAiReview"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { placeExtractTypeLabel } from "@/lib/place-extract-type-label"

type DuplicateClusterListProps = {
  clusters: Array<{ cluster_id: string; label: string; canonicals: CleanupClusterCanonical[] }>
  entityType: CleanupEntityType
  detailHref: (canonicalId: string) => string
  linkedRecordLabel: string
  canEdit?: boolean
  aiProposals?: CleanupAiProposal[]
  onMerge?: (sourceId: string, targetId: string) => void | Promise<void>
  onDeleteEmpty?: (canonicalId: string) => void | Promise<void>
  onDismissCluster?: (clusterId: string, memberIds: string[]) => void | Promise<void>
  onAcceptAiProposal?: (proposal: CleanupAiProposal) => void | Promise<void>
  onRejectAiProposal?: (proposal: CleanupAiProposal) => void | Promise<void>
}

function formatTypeLabel(
  entityType: CleanupEntityType,
  canonical: CleanupClusterCanonical,
): string {
  const typeValue =
    entityType === "person"
      ? canonical.person_type
      : entityType === "organization"
        ? canonical.organization_type
        : canonical.location_type
  if (!typeValue) {
    switch (entityType) {
      case "person":
        return "Person"
      case "organization":
        return "Organization"
      default:
        return "Location"
    }
  }
  return placeExtractTypeLabel(typeValue)
}

function formatCanonicalMeta(
  entityType: CleanupEntityType,
  canonical: CleanupClusterCanonical,
  linkedRecordLabel: string,
): string {
  const parts: string[] = [formatTypeLabel(entityType, canonical)]
  if (entityType === "person") {
    const title = (canonical.title ?? "").trim()
    const affiliation = (canonical.affiliation ?? "").trim()
    if (title) parts.push(title)
    if (affiliation) parts.push(affiliation)
  }
  parts.push(canonical.status)
  const linked = canonical.linked_substrate_count ?? 0
  const mentions = canonical.mention_count ?? 0
  parts.push(`${linked} ${linkedRecordLabel}`)
  parts.push(`${mentions} mentions`)
  return parts.join(" · ")
}

function isEmptyCanonical(canonical: CleanupClusterCanonical): boolean {
  return (canonical.linked_substrate_count ?? 0) === 0 && (canonical.mention_count ?? 0) === 0
}

function emptyClusterMessage(entityType: CleanupEntityType): string {
  switch (entityType) {
    case "person":
      return "No duplicate person names found in this stylebook."
    case "organization":
      return "No duplicate organization names found in this stylebook."
    default:
      return "No duplicate location names found in this stylebook."
  }
}

function formatProposalSummary(
  proposal: CleanupAiProposal,
  canonicals: CleanupClusterCanonical[],
): string {
  const labelById = new Map(canonicals.map((canonical) => [canonical.id, canonical.label]))
  if (proposal.action === "merge" && proposal.target_canonical_id) {
    const keeper = labelById.get(proposal.target_canonical_id) ?? "keeper record"
    const sources = proposal.member_ids
      .filter((memberId) => memberId !== proposal.target_canonical_id)
      .map((memberId) => labelById.get(memberId) ?? memberId)
    if (sources.length === 0) {
      return `Merge into "${keeper}"`
    }
    return `Merge ${sources.map((label) => `"${label}"`).join(", ")} into "${keeper}"`
  }
  const left = labelById.get(proposal.member_ids[0] ?? "") ?? proposal.member_ids[0]
  const right = labelById.get(proposal.member_ids[1] ?? "") ?? proposal.member_ids[1]
  return `Keep "${left}" and "${right}" separate`
}

export function DuplicateClusterList({
  clusters,
  entityType,
  detailHref,
  linkedRecordLabel,
  canEdit = false,
  aiProposals = [],
  onMerge,
  onDeleteEmpty,
  onDismissCluster,
  onAcceptAiProposal,
  onRejectAiProposal,
}: DuplicateClusterListProps) {
  const [dragSourceId, setDragSourceId] = useState<string | null>(null)
  const [dropTargetId, setDropTargetId] = useState<string | null>(null)

  if (clusters.length === 0) {
    return (
      <p className="text-muted-foreground py-8 text-center">{emptyClusterMessage(entityType)}</p>
    )
  }

  return (
    <div className="space-y-4">
      {canEdit ? (
        <p className="text-sm text-muted-foreground">
          Drag the duplicate you want to remove onto the record you want to keep. Linked records
          move to the keeper and the duplicate is deleted. Empty records can be deleted with the
          trash icon.
        </p>
      ) : null}
      {clusters.map((cluster) => {
        const clusterProposals = proposalsForCluster(aiProposals, cluster)
        return (
        <Card key={cluster.cluster_id}>
          <CardHeader className="pb-3">
            <div className="flex items-start justify-between gap-3">
              <div>
                <CardTitle className="text-base">
                  {cluster.label}
                  {cluster.label !== "Similar locations" &&
                  cluster.label !== "Similar people" &&
                  cluster.label !== "Similar organizations"
                    ? ` — ${cluster.canonicals.length} records`
                    : ` (${cluster.canonicals.length})`}
                </CardTitle>
                {canEdit && cluster.canonicals.length > 1 ? (
                  <CardDescription>
                    Drop a record here to merge into another in this group.
                  </CardDescription>
                ) : null}
              </div>
              {canEdit && onDismissCluster ? (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="shrink-0"
                  onClick={() =>
                    void onDismissCluster(
                      cluster.cluster_id,
                      cluster.canonicals.map((canonical) => canonical.id),
                    )
                  }
                >
                  Keep separate
                </Button>
              ) : null}
            </div>
            {clusterProposals.length > 0 ? (
              <div className="mt-3 space-y-2">
                {clusterProposals.map((proposal) => (
                  <div
                    key={proposal.id}
                    className="rounded-md border border-primary/20 bg-primary/5 px-3 py-2 text-sm"
                  >
                    <div className="flex items-start gap-2">
                      <Sparkles className="h-4 w-4 mt-0.5 shrink-0 text-primary" aria-hidden />
                      <div className="flex-1 min-w-0 space-y-1">
                        <p className="font-medium">
                          AI suggestion · {Math.round(proposal.confidence * 100)}% confidence
                        </p>
                        <p>{formatProposalSummary(proposal, cluster.canonicals)}</p>
                        {proposal.rationale ? (
                          <p className="text-muted-foreground">{proposal.rationale}</p>
                        ) : null}
                        {canEdit && onAcceptAiProposal && onRejectAiProposal ? (
                          <div className="flex flex-wrap gap-2 pt-1">
                            <Button
                              type="button"
                              size="sm"
                              onClick={() => void onAcceptAiProposal(proposal)}
                            >
                              Accept
                            </Button>
                            <Button
                              type="button"
                              size="sm"
                              variant="outline"
                              onClick={() => void onRejectAiProposal(proposal)}
                            >
                              Reject
                            </Button>
                          </div>
                        ) : null}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : null}
          </CardHeader>
          <CardContent className="space-y-2">
            {cluster.canonicals.map((canonical) => {
              const isDropTarget =
                canEdit &&
                dragSourceId !== null &&
                dropTargetId === canonical.id &&
                dragSourceId !== canonical.id
              return (
                <div
                  key={canonical.id}
                  draggable={canEdit && Boolean(onMerge)}
                  onDragStart={() => setDragSourceId(canonical.id)}
                  onDragEnd={() => {
                    setDragSourceId(null)
                    setDropTargetId(null)
                  }}
                  onDragOver={(event) => {
                    if (!canEdit || !onMerge || dragSourceId === canonical.id) return
                    event.preventDefault()
                    setDropTargetId(canonical.id)
                  }}
                  onDragLeave={() => {
                    if (dropTargetId === canonical.id) setDropTargetId(null)
                  }}
                  onDrop={(event) => {
                    event.preventDefault()
                    if (!canEdit || !onMerge || !dragSourceId || dragSourceId === canonical.id) {
                      return
                    }
                    void onMerge(dragSourceId, canonical.id)
                    setDragSourceId(null)
                    setDropTargetId(null)
                  }}
                  className={`flex items-start gap-2 border rounded-md px-3 py-2 transition-colors ${
                    isDropTarget ? "border-primary bg-primary/5 ring-2 ring-primary/30" : "hover:bg-muted/40"
                  } ${canEdit && onMerge ? "cursor-grab active:cursor-grabbing" : ""}`}
                >
                  {canEdit && onMerge ? (
                    <GripVertical
                      className="h-4 w-4 mt-1 shrink-0 text-muted-foreground"
                      aria-hidden
                    />
                  ) : null}
                  <div className="flex-1 min-w-0">
                    <Link
                      to={detailHref(canonical.id)}
                      className="font-medium text-primary hover:underline"
                      onClick={(event) => event.stopPropagation()}
                    >
                      {canonical.label}
                    </Link>
                    <span className="block text-sm text-muted-foreground">
                      {formatCanonicalMeta(entityType, canonical, linkedRecordLabel)}
                    </span>
                  </div>
                  {canEdit && onDeleteEmpty && isEmptyCanonical(canonical) ? (
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="shrink-0 text-muted-foreground hover:text-destructive"
                      aria-label={`Delete ${canonical.label}`}
                      onClick={() => void onDeleteEmpty(canonical.id)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  ) : null}
                </div>
              )
            })}
          </CardContent>
        </Card>
        )
      })}
    </div>
  )
}
