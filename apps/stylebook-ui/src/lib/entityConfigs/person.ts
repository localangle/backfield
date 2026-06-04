/**
 * Full EntityConfig for canonical people (catalog, candidates, pickers).
 */

import {
  acceptPersonCandidate,
  deferPersonCandidate,
  getPersonCandidateContext,
  listPersonCandidates,
} from "@/lib/stylebook-api/personCandidates"
import {
  getCanonicalPersonLegacy,
  linkPersonSubstrateToCanonical,
  listCanonicalPeopleLegacy,
  unlinkPersonSubstrateFromCanonical,
} from "@/lib/stylebook-api/people"
import type { EntityConfig } from "@/lib/entityTypes"

export interface PersonPickerRow {
  id: string
  project_id: number
  full_name: string
  title?: string
  affiliation?: string
  person_type?: string
  public_figure?: boolean
  status: string
  created_at: string
  updated_at: string
}

async function listPersonPickerRows(
  projectSlug: string,
  q?: string,
  _status?: string,
  limit: number = 100,
  offset: number = 0,
): Promise<{ people: PersonPickerRow[] }> {
  const res = await listCanonicalPeopleLegacy(projectSlug, q, limit, offset)
  return {
    people: res.canonicals.map((c) => ({
      id: c.id,
      project_id: 0,
      full_name: c.label,
      title: c.title ?? undefined,
      affiliation: c.affiliation ?? undefined,
      person_type: c.person_type ?? undefined,
      public_figure: c.public_figure,
      status: c.status,
      created_at: c.created_at,
      updated_at: c.updated_at,
    })),
  }
}

const notImplemented = async (): Promise<never> => {
  throw new Error("Not available in this Stylebook slice")
}

export const personConfig = {
  type: "person",
  displayName: { singular: "Person", plural: "People" },
  routes: {
    candidates: "/people/candidates",
    canonical: "/people/canonical",
    detail: "/people/canonical/:id",
  },
  api: {
    listCandidates: listPersonCandidates,
    listCanonical: listPersonPickerRows,
    listCanonicalForSelector: listPersonPickerRows,
    getDetail: (id: string | number, projectSlug: string) =>
      getCanonicalPersonLegacy(String(id), projectSlug),
    createCanonical: notImplemented,
    updateCanonical: notImplemented,
    deleteCanonical: notImplemented,
    acceptCandidate: (candidateId: number, projectSlug: string, data: unknown) =>
      acceptPersonCandidate(projectSlug, candidateId, data as Parameters<typeof acceptPersonCandidate>[2]),
    bulkAcceptCandidates: notImplemented,
    linkCandidateToExisting: (candidateId: number, projectSlug: string, canonicalId: string | number) =>
      linkPersonSubstrateToCanonical(candidateId, projectSlug, String(canonicalId)),
    createCanonicalFromCluster: notImplemented,
    getMentions: notImplemented,
    unlink: (id: number, projectSlug: string) =>
      unlinkPersonSubstrateFromCanonical(id, projectSlug),
    bulkUnlink: notImplemented,
    getMeta: notImplemented,
    createMeta: notImplemented,
    updateMeta: notImplemented,
    deleteMeta: notImplemented,
  },
  fields: [
    { key: "name", label: "Name", sortable: true },
    { key: "title", label: "Title", sortable: true },
    { key: "affiliation", label: "Affiliation", sortable: true },
  ],
  filters: [
    {
      key: "public_figure",
      label: "Public figure",
      type: "select",
      options: [
        { value: "all", label: "All" },
        { value: "yes", label: "Yes" },
        { value: "no", label: "No" },
      ],
    },
  ],
  getCandidateName: (candidate: unknown) => {
    const c = candidate as { suggested_name?: string }
    return (c.suggested_name ?? "").trim()
  },
  getCanonicalName: (c: PersonPickerRow) => c.full_name,
  getCandidateDisplayFields: (candidate: unknown) => {
    const c = candidate as {
      suggested_name?: string
      suggested_title?: string | null
      suggested_affiliation?: string | null
    }
    return {
      name: (c.suggested_name ?? "").trim(),
      title: (c.suggested_title ?? "").trim(),
      affiliation: (c.suggested_affiliation ?? "").trim(),
    }
  },
  getCanonicalDisplayFields: (c: PersonPickerRow) => ({
    name: c.full_name,
    title: c.title ?? "",
    affiliation: c.affiliation ?? "",
  }),
} as unknown as EntityConfig<PersonPickerRow>

export { deferPersonCandidate, getPersonCandidateContext, listPersonPickerRows }
