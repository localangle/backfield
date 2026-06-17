import { stylebookJsonFetch } from "@/lib/stylebook-api/client"
import type { CanonicalLocation, PaginatedCanonicalLocationResponse } from "@/lib/stylebook-api/locations"

export type CleanupCheckKind = "cluster" | "list"

export interface CleanupCheck {
  id: string
  title: string
  description: string
  entity_type: string
  kind: CleanupCheckKind
  count: number
}

export interface CleanupChecksResponse {
  checks: CleanupCheck[]
  total_open: number
}

export interface DuplicateLocationCluster {
  cluster_id: string
  label: string
  canonicals: CanonicalLocation[]
}

export interface PaginatedDuplicateClustersResponse {
  clusters: DuplicateLocationCluster[]
  total: number
  page: number
  per_page: number
  has_next: boolean
  has_prev: boolean
}

export interface ListCleanupChecksParams {
  stylebookSlug: string
  project?: string
}

export interface GetCleanupCheckResultsParams {
  stylebookSlug: string
  checkId: string
  project?: string
  page?: number
  perPage?: number
}

function cleanupChecksPath(stylebookSlug: string): string {
  return `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/cleanup/checks`
}

function cleanupCheckResultsPath(stylebookSlug: string, checkId: string): string {
  return `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/cleanup/checks/${encodeURIComponent(checkId)}`
}

export async function listCleanupChecks(
  params: ListCleanupChecksParams,
): Promise<CleanupChecksResponse> {
  const q = new URLSearchParams()
  if (params.project) q.set("project", params.project)
  const suffix = q.toString() ? `?${q.toString()}` : ""
  return stylebookJsonFetch<CleanupChecksResponse>(
    `${cleanupChecksPath(params.stylebookSlug)}${suffix}`,
  )
}

export async function getDuplicateLocationClusters(
  params: GetCleanupCheckResultsParams,
): Promise<PaginatedDuplicateClustersResponse> {
  const q = new URLSearchParams()
  if (params.project) q.set("project", params.project)
  const page = params.page ?? 1
  const perPage = params.perPage ?? 25
  q.set("limit", String(perPage))
  q.set("offset", String((page - 1) * perPage))
  return stylebookJsonFetch<PaginatedDuplicateClustersResponse>(
    `${cleanupCheckResultsPath(params.stylebookSlug, "duplicate-locations")}?${q.toString()}`,
  )
}

export async function getMissingGeometryLocations(
  params: GetCleanupCheckResultsParams,
): Promise<PaginatedCanonicalLocationResponse> {
  const q = new URLSearchParams()
  if (params.project) q.set("project", params.project)
  const page = params.page ?? 1
  const perPage = params.perPage ?? 25
  q.set("limit", String(perPage))
  q.set("offset", String((page - 1) * perPage))
  return stylebookJsonFetch<PaginatedCanonicalLocationResponse>(
    `${cleanupCheckResultsPath(params.stylebookSlug, "missing-geometry-locations")}?${q.toString()}`,
  )
}

export async function getCleanupCheckResults(
  params: GetCleanupCheckResultsParams,
): Promise<PaginatedDuplicateClustersResponse | PaginatedCanonicalLocationResponse> {
  if (params.checkId === "duplicate-locations") {
    return getDuplicateLocationClusters(params)
  }
  if (params.checkId === "missing-geometry-locations") {
    return getMissingGeometryLocations(params)
  }
  throw new Error(`Unknown cleanup check: ${params.checkId}`)
}
