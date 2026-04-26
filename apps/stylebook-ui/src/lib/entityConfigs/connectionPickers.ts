/**
 * EntityConfig objects for connection target pickers (canonical list APIs).
 * Person / organization / work use empty-list stubs until those entities are migrated.
 */

import { listCanonicalLocations } from "@/lib/stylebook-api/locations"
import { listOrganizations, listPeople, listWorks } from "@/lib/stylebook-api/entityListStubs"
import type { EntityConfig } from "@/lib/entityTypes"

/** Canonical location row as used by EntitySelector (name matches agate ``Location`` shape). */
export interface LocationPickerRow {
  id: number
  project_id: number
  name: string
  location_type: string
  status: string
  created_at: string
  updated_at: string
}

export interface PersonPickerRow {
  id: number
  project_id: number
  full_name: string
  title?: string
  affiliation?: string
  status: string
  created_at: string
  updated_at: string
}

export interface OrganizationPickerRow {
  id: number
  project_id: number
  name: string
  organization_type?: string
  status: string
  created_at: string
  updated_at: string
}

export interface WorkPickerRow {
  id: number
  project_id: number
  name: string
  work_type?: string
  status: string
  created_at: string
  updated_at: string
}

async function listLocationPickerRows(
  projectSlug: string,
  q?: string,
  _status?: string,
  limit: number = 100,
  offset: number = 0,
): Promise<{ locations: LocationPickerRow[] }> {
  const res = await listCanonicalLocations(projectSlug, q, limit, offset)
  return {
    locations: res.canonicals.map((c) => ({
      id: c.id,
      project_id: 0,
      name: c.label,
      location_type: c.location_type ?? "",
      status: c.status,
      created_at: c.created_at,
      updated_at: c.updated_at,
    })),
  }
}

const noopListCandidates = async () =>
  ({
    candidates: [],
    total: 0,
    limit: 100,
    offset: 0,
    has_next: false,
    has_prev: false,
  }) as const

const notImplemented = async (): Promise<never> => {
  throw new Error("Not available in this Stylebook slice")
}

export const locationPickerConfig = {
  type: "location",
  displayName: { singular: "Location", plural: "Locations" },
  routes: {
    candidates: "/locations/candidates",
    canonical: "/locations/canonical",
    detail: "/locations/canonical/:id",
  },
  api: {
    listCandidates: noopListCandidates,
    listCanonical: listLocationPickerRows,
    listCanonicalForSelector: listLocationPickerRows,
    getDetail: notImplemented,
    createCanonical: notImplemented,
    updateCanonical: notImplemented,
    deleteCanonical: notImplemented,
    acceptCandidate: notImplemented,
    bulkAcceptCandidates: notImplemented,
    linkCandidateToExisting: notImplemented,
    createCanonicalFromCluster: notImplemented,
    getMentions: notImplemented,
    unlink: notImplemented,
    bulkUnlink: notImplemented,
    getMeta: notImplemented,
    createMeta: notImplemented,
    updateMeta: notImplemented,
    deleteMeta: notImplemented,
  },
  fields: [
    { key: "name", label: "Name", sortable: true },
    { key: "type", label: "Type", sortable: true },
    { key: "address", label: "Address", sortable: true },
  ],
  filters: [],
  getCandidateName: () => "",
  getCanonicalName: (c: LocationPickerRow) => c.name,
  getCandidateDisplayFields: () => ({ name: "", type: "", address: "" }),
  getCanonicalDisplayFields: (c: LocationPickerRow) => ({
    name: c.name,
    type: c.location_type || "",
    address: "",
  }),
} as unknown as EntityConfig<LocationPickerRow>

export const personPickerConfig = {
  type: "person",
  displayName: { singular: "Person", plural: "People" },
  routes: {
    candidates: "/people/candidates",
    canonical: "/people/canonical",
    detail: "/people/canonical/:id",
  },
  api: {
    listCandidates: noopListCandidates,
    listCanonical: listPeople,
    listCanonicalForSelector: listPeople,
    getDetail: notImplemented,
    createCanonical: notImplemented,
    updateCanonical: notImplemented,
    deleteCanonical: notImplemented,
    acceptCandidate: notImplemented,
    bulkAcceptCandidates: notImplemented,
    linkCandidateToExisting: notImplemented,
    createCanonicalFromCluster: notImplemented,
    getMentions: notImplemented,
    unlink: notImplemented,
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
  filters: [],
  getCandidateName: () => "",
  getCanonicalName: (c: PersonPickerRow) => c.full_name,
  getCandidateDisplayFields: () => ({ name: "", title: "", affiliation: "" }),
  getCanonicalDisplayFields: (c: PersonPickerRow) => ({
    name: c.full_name,
    title: c.title ?? "",
    affiliation: c.affiliation ?? "",
  }),
} as unknown as EntityConfig<PersonPickerRow>

export const organizationPickerConfig = {
  type: "organization",
  displayName: { singular: "Organization", plural: "Organizations" },
  routes: {
    candidates: "/organizations/candidates",
    canonical: "/organizations/canonical",
    detail: "/organizations/canonical/:id",
  },
  api: {
    listCandidates: noopListCandidates,
    listCanonical: listOrganizations,
    listCanonicalForSelector: listOrganizations,
    getDetail: notImplemented,
    createCanonical: notImplemented,
    updateCanonical: notImplemented,
    deleteCanonical: notImplemented,
    acceptCandidate: notImplemented,
    bulkAcceptCandidates: notImplemented,
    linkCandidateToExisting: notImplemented,
    createCanonicalFromCluster: notImplemented,
    getMentions: notImplemented,
    unlink: notImplemented,
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
  getCandidateName: () => "",
  getCanonicalName: (c: OrganizationPickerRow) => c.name,
  getCandidateDisplayFields: () => ({ name: "", type: "" }),
  getCanonicalDisplayFields: (c: OrganizationPickerRow) => ({
    name: c.name,
    type: c.organization_type ?? "",
  }),
} as unknown as EntityConfig<OrganizationPickerRow>

export const workPickerConfig = {
  type: "work",
  displayName: { singular: "Work", plural: "Works" },
  routes: {
    candidates: "/works/candidates",
    canonical: "/works/canonical",
    detail: "/works/canonical/:id",
  },
  api: {
    listCandidates: noopListCandidates,
    listCanonical: listWorks,
    listCanonicalForSelector: listWorks,
    getDetail: notImplemented,
    createCanonical: notImplemented,
    updateCanonical: notImplemented,
    deleteCanonical: notImplemented,
    acceptCandidate: notImplemented,
    bulkAcceptCandidates: notImplemented,
    linkCandidateToExisting: notImplemented,
    createCanonicalFromCluster: notImplemented,
    getMentions: notImplemented,
    unlink: notImplemented,
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
  getCandidateName: () => "",
  getCanonicalName: (c: WorkPickerRow) => c.name,
  getCandidateDisplayFields: () => ({ name: "", type: "" }),
  getCanonicalDisplayFields: (c: WorkPickerRow) => ({
    name: c.name,
    type: c.work_type ?? "",
  }),
} as unknown as EntityConfig<WorkPickerRow>
