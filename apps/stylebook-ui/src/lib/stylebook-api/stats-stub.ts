import { stylebookJsonFetch } from "@/lib/stylebook-api/client"

export interface EntityTypeStats {
  canonical_count: number
  candidate_count: number
}

export interface Stats {
  locations: EntityTypeStats
  people: EntityTypeStats
  organizations: EntityTypeStats
  works: EntityTypeStats
}

export async function getStats(projectSlug: string): Promise<Stats> {
  const params = new URLSearchParams({ project_slug: projectSlug })
  return stylebookJsonFetch<Stats>(`/v1/stats?${params}`)
}

export interface AgentType {
  type: string
  label: string
  description?: string
  icon?: string
}

export async function getAgentTypes(projectSlug: string): Promise<AgentType[]> {
  const params = new URLSearchParams({ project_slug: projectSlug })
  return stylebookJsonFetch<AgentType[]>(`/v1/agents/types?${params}`)
}
