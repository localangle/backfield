import { useState, useEffect } from "react"
import { useNavigate } from "react-router-dom"
import { getStats, type Stats } from "@/lib/api"
import { useProjectCatalogScope } from "@/lib/catalogNavigation"
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
import { MapPin, Users, Building2, BookOpen, Loader2 } from "lucide-react"

export default function Index() {
  const navigate = useNavigate()
  const {
    projectScopeSlug,
    workflowScopeSuffix,
    filterScopeSuffix,
    stylebookSlug,
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

  const handleEntityTypeClick = (type: string) => {
    if (type === "locations") {
      navigate(`/locations/canonical${filterScopeSuffix}`)
    } else if (type === "people") {
      navigate(`/people/candidates${workflowScopeSuffix}`)
    } else if (type === "organizations") {
      navigate(`/organizations/candidates${workflowScopeSuffix}`)
    } else if (type === "works") {
      navigate(`/works/candidates${workflowScopeSuffix}`)
    }
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
          <Card
            className="cursor-pointer hover:shadow-md transition-shadow"
            onClick={() => handleEntityTypeClick("locations")}
          >
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="text-lg">Locations</CardTitle>
                <MapPin className="h-5 w-5 text-muted-foreground" />
              </div>
              <CardDescription>Canonical places and locations</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="text-sm text-muted-foreground">
                Canonicals are stylebook-scoped. Evidence can be filtered by project.
              </div>
            </CardContent>
          </Card>

          <Card className="opacity-60">
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="text-lg">People</CardTitle>
                <Users className="h-5 w-5 text-muted-foreground" />
              </div>
              <CardDescription>Canonical people</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="text-sm text-muted-foreground">
                Select a project to view candidates.
              </div>
            </CardContent>
          </Card>

          <Card className="opacity-60">
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="text-lg">Organizations</CardTitle>
                <Building2 className="h-5 w-5 text-muted-foreground" />
              </div>
              <CardDescription>Canonical organizations and institutions</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="text-sm text-muted-foreground">
                Select a project to view candidates.
              </div>
            </CardContent>
          </Card>

          <Card className="opacity-60">
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="text-lg">Works</CardTitle>
                <BookOpen className="h-5 w-5 text-muted-foreground" />
              </div>
              <CardDescription>
                Canonical works (laws, reports, books, products, artworks)
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="text-sm text-muted-foreground">
                Select a project to view candidates.
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    )
  }

  const entityTypes = [
    {
      id: "locations",
      name: "Locations",
      icon: MapPin,
      stats: stats.locations,
      description: "Canonical places and locations",
    },
    {
      id: "people",
      name: "People",
      icon: Users,
      stats: stats.people,
      description: "Canonical people",
    },
    {
      id: "organizations",
      name: "Organizations",
      icon: Building2,
      stats: stats.organizations ?? {
        canonical_count: 0,
        candidate_count: 0,
      },
      description: "Canonical organizations and institutions",
    },
    {
      id: "works",
      name: "Works",
      icon: BookOpen,
      stats: stats.works ?? { canonical_count: 0, candidate_count: 0 },
      description:
        "Canonical works (laws, reports, books, products, artworks)",
    },
  ]

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
              onClick={() => handleEntityTypeClick(entityType.id)}
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
