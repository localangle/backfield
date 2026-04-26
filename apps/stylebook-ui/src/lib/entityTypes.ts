/**
 * Entity definitions for Stylebook canonical pickers (ported from agate stylebook-ui).
 */

export type EntityType = "location" | "person" | "organization" | "work"

export interface FieldConfig {
  key: string
  label: string
  sortable?: boolean
  displayValue?: (candidate: unknown) => string
}

export interface FilterConfig {
  key: string
  label: string
  type: "text" | "select" | "boolean" | "number"
  options?: Array<{ value: string; label: string }>
  getValue?: (candidate: unknown) => unknown
}

export interface TransformConfig {
  key: string
  label: string
  description?: string
  handler: (projectSlug: string, candidateIds: number[], ...args: unknown[]) => Promise<unknown>
}

export interface RouteConfig {
  candidates: string
  canonical: string
  detail: string
}

export interface ApiConfig<T> {
  listCandidates: (projectSlug: string, status: string, cluster: boolean, options?: unknown) => Promise<unknown>
  listCanonical: (
    projectSlug: string,
    q?: string,
    status?: string,
    limit?: number,
    offset?: number,
  ) => Promise<unknown>
  listCanonicalForSelector?: (
    projectSlug: string,
    q?: string,
    status?: string,
    limit?: number,
    offset?: number,
  ) => Promise<unknown>
  getDetail: (id: number, projectSlug: string) => Promise<T>
  createCanonical: (projectSlug: string, data: unknown) => Promise<T>
  updateCanonical: (id: number, projectSlug: string, data: unknown) => Promise<T>
  deleteCanonical: (id: number, projectSlug: string) => Promise<unknown>
  acceptCandidate: (candidateId: number, projectSlug: string, data: unknown) => Promise<unknown>
  bulkAcceptCandidates: (projectSlug: string, data: unknown) => Promise<unknown>
  linkCandidateToExisting: (candidateId: number, projectSlug: string, canonicalId: number) => Promise<unknown>
  createCanonicalFromCluster: (
    projectSlug: string,
    candidateIds: number[],
    useRepresentative?: boolean,
  ) => Promise<unknown>
  getMentions: (
    id: number,
    projectSlug: string,
    limit?: number,
    offset?: number,
    sort?: string,
    sortDirection?: "asc" | "desc",
  ) => Promise<unknown>
  unlink: (id: number, projectSlug: string, data: unknown) => Promise<unknown>
  bulkUnlink: (id: number, projectSlug: string, links: unknown[]) => Promise<unknown>
  getMeta: (id: number, projectSlug: string) => Promise<unknown>
  createMeta: (id: number, projectSlug: string, data: unknown) => Promise<unknown>
  updateMeta: (id: number, metaId: number, projectSlug: string, data: unknown) => Promise<unknown>
  deleteMeta: (id: number, metaId: number, projectSlug: string) => Promise<unknown>
}

export interface EntityConfig<T> {
  type: EntityType
  displayName: {
    singular: string
    plural: string
  }
  routes: RouteConfig
  api: ApiConfig<T>
  fields: FieldConfig[]
  filters: FilterConfig[]
  transforms?: TransformConfig[]
  clusterByField?: string
  supportsGeometry?: boolean
  getCandidateName: (candidate: unknown) => string
  getCanonicalName: (canonical: T) => string
  getCandidateDisplayFields: (candidate: unknown) => Record<string, string>
  getCanonicalDisplayFields: (canonical: T) => Record<string, string>
}
