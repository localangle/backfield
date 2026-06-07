import { useState, useEffect } from "react"
import { useNavigate } from "react-router-dom"
import { getStats, type Stats } from "@/lib/api"
import { useProjectCatalogScope } from "@/lib/catalogNavigation"
import { ENTITY_HOME_CARDS, entityDisplayName } from "@/lib/entityRegistry"
import { useSelectedStylebookLabel } from "@/lib/stylebookScopeContext"
import { Breadcrumbs } from "@/components/Breadcrumbs"
import { useScopeBreadcrumbRoot } from "@/lib/breadcrumbs"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Loader2 } from "lucide-react"

const ENTITY_STATS_KEYS: Record<
  (typeof ENTITY_HOME_CARDS)[number]["entityType"],
  keyof Stats
> = {
  location: "locations",
  person: "people",
  organization: "organizations",
}

function entityStatsKey(entityType: (typeof ENTITY_HOME_CARDS)[number]["entityType"]): keyof Stats {
  return ENTITY_STATS_KEYS[entityType]
}

export default function Index() {
  const navigate = useNavigate()
  const {
    projectScopeSlug,
    workflowScopeSuffix,
    filterScopeSuffix,
    stylebookSlug,
    catalogBasePath,
  } = useProjectCatalogScope()
  const selectedStylebookLabel = useSelectedStylebookLabel()
  const crumbRoot = useScopeBreadcrumbRoot()
  const [stats, setStats] = useState<Stats | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (projectScopeSlug) {
      loadStats(projectScopeSlug)
    } else {
      setLoading(false)
      setStats(null)
    }
  }, [projectScopeSlug, stylebookSlug])

  const loadStats = async (slug: string) => {
    try {
      setLoading(true)
      const data = await getStats(slug)
      setStats(data)
    } catch (error) {
      console.error("Failed to load stats:", error)
    } finally {
      setLoading(false)
    }
  }

  const handleEntityTypeClick = (card: (typeof ENTITY_HOME_CARDS)[number]) => {
    const suffix = card.canonicalFirst ? filterScopeSuffix : workflowScopeSuffix
    const pathSegment = card.canonicalFirst ? "canonical" : "candidates"
    navigate(`${catalogBasePath}/${card.routeSegment}/${pathSegment}${suffix}`)
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (!stats) {
    return (
      <div className="space-y-6">
        <div>
          <Breadcrumbs items={[{ label: crumbRoot.label }]} className="mb-3" />
          <h1 className="text-3xl font-bold">{selectedStylebookLabel}</h1>
          <p className="text-muted-foreground mt-2">
            Manage canonical entities and review candidates
          </p>
        </div>

        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
          {ENTITY_HOME_CARDS.map((card) => {
            const Icon = card.icon
            const isLocation = card.entityType === "location"
            return (
              <Card
                key={card.entityType}
                className={
                  isLocation
                    ? "cursor-pointer hover:shadow-md transition-shadow"
                    : "opacity-60"
                }
                onClick={isLocation ? () => handleEntityTypeClick(card) : undefined}
              >
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-lg">
                      {entityDisplayName(card.entityType, true)}
                    </CardTitle>
                    <Icon className="h-5 w-5 text-muted-foreground" />
                  </div>
                  <CardDescription>{card.description}</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="text-sm text-muted-foreground">
                    {isLocation
                      ? "Canonicals are stylebook-scoped. Evidence can be filtered by project."
                      : "Select a project to view candidates."}
                  </div>
                </CardContent>
              </Card>
            )
          })}
        </div>
      </div>
    )
  }

  const entityTypes = ENTITY_HOME_CARDS.map((card) => ({
    id: card.routeSegment,
    name: entityDisplayName(card.entityType, true),
    icon: card.icon,
    stats:
      stats[entityStatsKey(card.entityType)] ??
      ({ canonical_count: 0, candidate_count: 0 } as Stats["people"]),
    description: card.description,
    card,
  }))

  return (
    <div className="space-y-6">
      <div>
        <Breadcrumbs items={[{ label: crumbRoot.label }]} className="mb-3" />
        <h1 className="text-3xl font-bold">{selectedStylebookLabel}</h1>
        <p className="text-muted-foreground mt-2">
          Manage canonical entities and review candidates
        </p>
      </div>

      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
        {entityTypes.map((entityType) => {
          const Icon = entityType.icon
          return (
            <Card
              key={entityType.id}
              className="cursor-pointer hover:shadow-lg transition-shadow"
              onClick={() => handleEntityTypeClick(entityType.card)}
            >
              <CardHeader>
                <div className="flex items-center gap-3">
                  <div className="p-2 bg-primary/10 rounded-lg">
                    <Icon className="h-6 w-6 text-primary" />
                  </div>
                  <div>
                    <CardTitle>{entityType.name}</CardTitle>
                    <CardDescription className="mt-1">
                      {entityType.description}
                    </CardDescription>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-muted-foreground">
                      Canonical items
                    </span>
                    <span className="text-2xl font-bold">
                      {entityType.stats.canonical_count.toLocaleString()}
                    </span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-muted-foreground">
                      Pending candidates
                    </span>
                    <span
                      className={`text-2xl font-bold ${
                        entityType.stats.candidate_count > 0
                          ? "text-orange-600"
                          : "text-muted-foreground"
                      }`}
                    >
                      {entityType.stats.candidate_count.toLocaleString()}
                    </span>
                  </div>
                </div>
              </CardContent>
            </Card>
          )
        })}
      </div>
    </div>
  )
}
