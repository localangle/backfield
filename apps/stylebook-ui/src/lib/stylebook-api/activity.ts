import { stylebookJsonFetch } from "@/lib/stylebook-api/client"

export interface StylebookActivityEvent {
  id: number
  stylebook_id: number
  project_id?: number | null
  actor_type: string
  actor_user_id?: number | null
  source: string
  event_type: string
  entity_type?: string | null
  entity_id?: string | null
  entity_label?: string | null
  related_entity_type?: string | null
  related_entity_id?: string | null
  related_entity_label?: string | null
  payload_json?: Record<string, unknown> | null
  created_at: string
}

export interface PaginatedStylebookActivityResponse {
  events: StylebookActivityEvent[]
  total: number
  page: number
  per_page: number
  has_next: boolean
  has_prev: boolean
}

export interface ListStylebookActivityParams {
  stylebookSlug: string
  page?: number
  perPage?: number
  eventType?: string
  entityType?: string
  source?: string
}

export async function listStylebookActivity(
  params: ListStylebookActivityParams,
): Promise<PaginatedStylebookActivityResponse> {
  const q = new URLSearchParams()
  const page = params.page ?? 1
  const perPage = params.perPage ?? 25
  q.set("limit", String(perPage))
  q.set("offset", String((page - 1) * perPage))
  if (params.eventType?.trim()) q.set("event_type", params.eventType.trim())
  if (params.entityType?.trim()) q.set("entity_type", params.entityType.trim())
  if (params.source?.trim()) q.set("source", params.source.trim())
  return stylebookJsonFetch<PaginatedStylebookActivityResponse>(
    `/v1/stylebooks/${encodeURIComponent(params.stylebookSlug)}/activity?${q.toString()}`,
  )
}
