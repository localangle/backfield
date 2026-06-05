/**
 * Full EntityConfig for canonical organizations (catalog, candidates, pickers).
 */

import {
  acceptOrganizationCandidate,
  deferOrganizationCandidate,
  getOrganizationCandidateContext,
  listOrganizationCandidates,
} from "@/lib/stylebook-api/organizationCandidates"
import {
  linkOrganizationSubstrateToCanonical,
  listCanonicalOrganizations,
  unlinkOrganizationSubstrateFromCanonical,
} from "@/lib/stylebook-api/organizations"
import type { EntityConfig } from "@/lib/entityTypes"

export interface OrganizationPickerRow {
  id: string
  project_id: number
  name: string
  organization_type?: string
  status: string
  created_at: string
  updated_at: string
}

export function createListOrganizationPickerRows(stylebookSlug: string) {
  return async function listOrganizationPickerRows(
    projectSlug: string,
    q?: string,
    _status?: string,
    limit: number = 100,
    offset: number = 0,
  ): Promise<{ organizations: OrganizationPickerRow[] }> {
    const res = await listCanonicalOrganizations(
      stylebookSlug,
      q,
      limit,
      offset,
      undefined,
      projectSlug,
    )
    return {
      organizations: res.canonicals.map((c) => ({
        id: c.id,
        project_id: 0,
        name: c.label,
        organization_type: c.organization_type ?? undefined,
        status: c.status,
        created_at: c.created_at,
        updated_at: c.updated_at,
      })),
    }
  }
}

const notImplemented = async (): Promise<never> => {
  throw new Error("Not available in this Stylebook slice")
}

export const organizationConfig = {
  type: "organization",
  displayName: { singular: "Organization", plural: "Organizations" },
  routes: {
    candidates: "/organizations/candidates",
    canonical: "/organizations/canonical",
    detail: "/organizations/canonical/:id",
  },
  api: {
    listCandidates: listOrganizationCandidates,
    listCanonical: notImplemented,
    listCanonicalForSelector: notImplemented,
    getDetail: notImplemented,
    createCanonical: notImplemented,
    updateCanonical: notImplemented,
    deleteCanonical: notImplemented,
    acceptCandidate: (candidateId: number, projectSlug: string, data: unknown) =>
      acceptOrganizationCandidate(
        projectSlug,
        candidateId,
        data as Parameters<typeof acceptOrganizationCandidate>[2],
      ),
    bulkAcceptCandidates: notImplemented,
    linkCandidateToExisting: (candidateId: number, projectSlug: string, canonicalId: string | number) =>
      linkOrganizationSubstrateToCanonical(candidateId, projectSlug, String(canonicalId)),
    createCanonicalFromCluster: notImplemented,
    getMentions: notImplemented,
    unlink: (id: number, projectSlug: string) =>
      unlinkOrganizationSubstrateFromCanonical(id, projectSlug),
    bulkUnlink: notImplemented,
    getMeta: notImplemented,
    createMeta: notImplemented,
    updateMeta: notImplemented,
    deleteMeta: notImplemented,
  },
  fields: [
    { key: "name", label: "Name", sortable: true },
    { key: "type", label: "Type", sortable: true },
  ],
  filters: [],
  getCandidateName: (candidate: unknown) => {
    const c = candidate as { suggested_name?: string }
    return (c.suggested_name ?? "").trim()
  },
  getCanonicalName: (c: OrganizationPickerRow) => c.name,
  getCandidateDisplayFields: (candidate: unknown) => {
    const c = candidate as {
      suggested_name?: string
      suggested_type?: string | null
    }
    return {
      name: (c.suggested_name ?? "").trim(),
      type: (c.suggested_type ?? "").trim(),
    }
  },
  getCanonicalDisplayFields: (c: OrganizationPickerRow) => ({
    name: c.name,
    type: c.organization_type ?? "",
  }),
} as unknown as EntityConfig<OrganizationPickerRow>

export { deferOrganizationCandidate, getOrganizationCandidateContext }
