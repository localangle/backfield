import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { getStats, getAgentTypes, type AgentType, type Stats } from '@/lib/api'
import { useProjectCatalogScope } from '@/lib/catalogNavigation'
import { useSelectedStylebookLabel } from '@/lib/stylebookScopeContext'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { MapPin, Users, Building2, BookOpen, Loader2, Link, Merge } from 'lucide-react'

const AGENT_ICON_MAP: Record<string, React.ComponentType<{ className?: string }>> = {
  Link,
  Merge,
  MapPin,
  Users,
  Building2,
  BookOpen,
}

export default function Index() {
  const navigate = useNavigate()
  const { projectSlug, scopeSuffix, stylebookSlug } = useProjectCatalogScope()
  const selectedStylebookLabel = useSelectedStylebookLabel()
  const [stats, setStats] = useState<Stats | null>(null)
  const [agents, setAgents] = useState<AgentType[]>([])
  const [loading, setLoading] = useState(true)
  const [agentsLoading, setAgentsLoading] = useState(false)

  useEffect(() => {
    if (projectSlug) {
      loadStats(projectSlug)
    } else {
      setLoading(false)
      setStats(null)
    }
  }, [projectSlug, stylebookSlug])

  useEffect(() => {
    if (projectSlug) {
      loadAgents(projectSlug)
    } else {
      setAgents([])
    }
  }, [projectSlug, stylebookSlug])

  const loadAgents = async (slug: string) => {
    try {
      setAgentsLoading(true)
      const data = await getAgentTypes(slug)
      setAgents(data)
    } catch (error) {
      console.error('Failed to load agents:', error)
      setAgents([])
    } finally {
      setAgentsLoading(false)
    }
  }

  const loadStats = async (slug: string) => {
    try {
      setLoading(true)
      const data = await getStats(slug)
      setStats(data)
    } catch (error) {
      console.error('Failed to load stats:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleEntityTypeClick = (type: string) => {
    if (type === 'locations') {
      navigate(`/locations/canonical${scopeSuffix}`)
    } else if (type === 'people') {
      navigate(`/people/candidates${scopeSuffix}`)
    } else if (type === 'organizations') {
      navigate(`/organizations/candidates${scopeSuffix}`)
    } else if (type === 'works') {
      navigate(`/works/candidates${scopeSuffix}`)
    }
  }

  if (loading || !projectSlug) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (!stats) {
    return (
      <div className="text-center py-12">
        <p className="text-muted-foreground">Failed to load statistics</p>
      </div>
    )
  }

  const entityTypes = [
    {
      id: 'locations',
      name: 'Locations',
      icon: MapPin,
      stats: stats.locations,
      description: 'Canonical places and locations',
    },
    {
      id: 'people',
      name: 'People',
      icon: Users,
      stats: stats.people,
      description: 'Canonical people',
    },
    {
      id: 'organizations',
      name: 'Organizations',
      icon: Building2,
      stats: stats.organizations ?? { canonical_count: 0, candidate_count: 0 },
      description: 'Canonical organizations and institutions',
    },
    {
      id: 'works',
      name: 'Works',
      icon: BookOpen,
      stats: stats.works ?? { canonical_count: 0, candidate_count: 0 },
      description: 'Canonical works (laws, reports, books, products, artworks)',
    },
  ]

  const handleAgentClick = (agentType: string) => {
    navigate(`/agents/${agentType}${scopeSuffix}`)
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">{selectedStylebookLabel}</h1>
        <p className="text-muted-foreground mt-2">
          Manage canonical entities and review candidates
        </p>
      </div>

      <Tabs defaultValue="entities" className="w-full space-y-6">
        <TabsList className="grid w-full grid-cols-2">
          <TabsTrigger value="entities">Entities</TabsTrigger>
          <TabsTrigger value="agents">Agents</TabsTrigger>
        </TabsList>
        <TabsContent value="entities">
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
                    <span className="text-sm text-muted-foreground">Canonical items</span>
                    <span className="text-2xl font-bold">{entityType.stats.canonical_count.toLocaleString()}</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-muted-foreground">Pending candidates</span>
                    <span className={`text-2xl font-bold ${entityType.stats.candidate_count > 0 ? 'text-orange-600' : 'text-muted-foreground'}`}>
                      {entityType.stats.candidate_count.toLocaleString()}
                    </span>
                  </div>
                </div>
              </CardContent>
            </Card>
          )
        })}
      </div>
        </TabsContent>
        <TabsContent value="agents">
          {agentsLoading ? (
            <div className="flex items-center justify-center min-h-[200px]">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          ) : agents.length === 0 ? (
            <div className="text-center py-12">
              <p className="text-muted-foreground">No agents available</p>
            </div>
          ) : (
            <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
              {agents.map((agent) => {
                const IconComponent = AGENT_ICON_MAP[agent.icon || ''] || Link
                return (
                  <Card
                    key={agent.type}
                    className="cursor-pointer hover:shadow-lg transition-shadow"
                    onClick={() => handleAgentClick(agent.type)}
                  >
                    <CardHeader>
                      <div className="flex items-center gap-3">
                        <div className="p-2 bg-primary/10 rounded-lg">
                          <IconComponent className="h-6 w-6 text-primary" />
                        </div>
                        <div>
                          <CardTitle>{agent.label}</CardTitle>
                          <CardDescription className="mt-1">
                            {agent.description || ''}
                          </CardDescription>
                        </div>
                      </div>
                    </CardHeader>
                  </Card>
                )
              })}
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  )
}
