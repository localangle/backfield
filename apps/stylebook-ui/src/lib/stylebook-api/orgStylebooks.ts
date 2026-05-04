import { stylebookJsonFetch } from "@/lib/stylebook-api/client"

export interface OrgStylebookRow {
  id: number
  organization_id: number
  name: string
  slug: string
  is_default: boolean
  created_at: string
  updated_at: string
}

export async function fetchOrganizationStylebooks(orgId: number): Promise<OrgStylebookRow[]> {
  return stylebookJsonFetch<OrgStylebookRow[]>(`/v1/organizations/${orgId}/stylebooks`)
}
