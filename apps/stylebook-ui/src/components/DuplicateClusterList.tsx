import { Link } from "react-router-dom"
import type { CanonicalLocation } from "@/lib/api"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { placeExtractTypeLabel } from "@/lib/place-extract-type-label"

type DuplicateClusterListProps = {
  clusters: Array<{ cluster_id: string; canonicals: CanonicalLocation[] }>
  locationDetailHref: (canonicalId: string) => string
}

function formatCanonicalMeta(canonical: CanonicalLocation): string {
  const typeLabel = canonical.location_type
    ? placeExtractTypeLabel(canonical.location_type)
    : "Location"
  const linked = canonical.linked_substrate_count ?? 0
  const mentions = canonical.mention_count ?? 0
  return `${typeLabel} · ${canonical.status} · ${linked} linked · ${mentions} mentions`
}

export function DuplicateClusterList({ clusters, locationDetailHref }: DuplicateClusterListProps) {
  if (clusters.length === 0) {
    return (
      <p className="text-muted-foreground py-8 text-center">
        No possible duplicate groups found at the current similarity threshold.
      </p>
    )
  }

  return (
    <div className="space-y-4">
      {clusters.map((cluster) => (
        <Card key={cluster.cluster_id}>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">
              {cluster.canonicals.length} similar locations
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {cluster.canonicals.map((canonical) => (
              <div
                key={canonical.id}
                className="flex flex-col gap-1 border rounded-md px-3 py-2 hover:bg-muted/40"
              >
                <Link
                  to={locationDetailHref(canonical.id)}
                  className="font-medium text-primary hover:underline"
                >
                  {canonical.label}
                </Link>
                <span className="text-sm text-muted-foreground">
                  {formatCanonicalMeta(canonical)}
                </span>
              </div>
            ))}
          </CardContent>
        </Card>
      ))}
    </div>
  )
}
