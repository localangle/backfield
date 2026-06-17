import { stylebookJsonFetch } from "@/lib/stylebook-api/client"
import type { PaginatedCleanupLocationIssuesResponse } from "@/lib/stylebook-api/cleanup"

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

export interface CleanupClusterCanonical {
  id: string
  label: string
  status: string
  linked_substrate_count?: number
  mention_count?: number
  location_type?: string | null
  person_type?: string | null
  organization_type?: string | null
  title?: string | null
  affiliation?: string | null
}

export interface DuplicateCluster {
  cluster_id: string
  label: string
  canonicals: CleanupClusterCanonical[]
}

/** @deprecated Use DuplicateCluster */
export type DuplicateLocationCluster = DuplicateCluster

export interface PaginatedDuplicateClustersResponse {
  clusters: DuplicateCluster[]
  total: number
  page: number
  per_page: number
  has_next: boolean
  has_prev: boolean
}

export type LocationGeographyIssueKind = "missing_geometry" | "distant_linked_places"

export interface CleanupLocationIssue {
  id: string
  slug: string
  label: string
  location_type?: string | null
  formatted_address?: string | null
  geometry_json?: Record<string, unknown> | null
  geometry_type?: string | null
  status: string
  linked_substrate_count: number
  mention_count: number
  created_at: string
  updated_at: string
  geography_issue: LocationGeographyIssueKind
  distant_linked_count: number
}

export interface PaginatedCleanupLocationIssuesResponse {
  canonicals: CleanupLocationIssue[]
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

function paginatedClusterQuery(params: GetCleanupCheckResultsParams): string {
  const q = new URLSearchParams()
  if (params.project) q.set("project", params.project)
  const page = params.page ?? 1
  const perPage = params.perPage ?? 25
  q.set("limit", String(perPage))
  q.set("offset", String((page - 1) * perPage))
  return q.toString()
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
  return stylebookJsonFetch<PaginatedDuplicateClustersResponse>(
    `${cleanupCheckResultsPath(params.stylebookSlug, "duplicate-locations")}?${paginatedClusterQuery(params)}`,
  )
}

export async function getDuplicatePersonClusters(
  params: GetCleanupCheckResultsParams,
): Promise<PaginatedDuplicateClustersResponse> {
  return stylebookJsonFetch<PaginatedDuplicateClustersResponse>(
    `${cleanupCheckResultsPath(params.stylebookSlug, "duplicate-people")}?${paginatedClusterQuery(params)}`,
  )
}

export async function getDuplicateOrganizationClusters(
  params: GetCleanupCheckResultsParams,
): Promise<PaginatedDuplicateClustersResponse> {
  return stylebookJsonFetch<PaginatedDuplicateClustersResponse>(
    `${cleanupCheckResultsPath(params.stylebookSlug, "duplicate-organizations")}?${paginatedClusterQuery(params)}`,
  )
}

export async function getMissingGeometryLocations(
  params: GetCleanupCheckResultsParams,
): Promise<PaginatedCleanupLocationIssuesResponse> {
  const q = new URLSearchParams()
  if (params.project) q.set("project", params.project)
  const page = params.page ?? 1
  const perPage = params.perPage ?? 25
  q.set("limit", String(perPage))
  q.set("offset", String((page - 1) * perPage))
  return stylebookJsonFetch<PaginatedCleanupLocationIssuesResponse>(
    `${cleanupCheckResultsPath(params.stylebookSlug, "missing-geometry-locations")}?${q.toString()}`,
  )
}

export async function getCleanupCheckResults(
  params: GetCleanupCheckResultsParams,
): Promise<PaginatedDuplicateClustersResponse | PaginatedCleanupLocationIssuesResponse> {
  switch (params.checkId) {
    case "duplicate-locations":
      return getDuplicateLocationClusters(params)
    case "duplicate-people":
      return getDuplicatePersonClusters(params)
    case "duplicate-organizations":
      return getDuplicateOrganizationClusters(params)
    case "missing-geometry-locations":
      return getMissingGeometryLocations(params)
    default:
      throw new Error(`Unknown cleanup check: ${params.checkId}`)
  }
}

export interface MergeCleanupCanonicalResponse {
  source_id: string
  target_id: string
  relinked_substrate_count: number
  source_deleted: boolean
}

/** @deprecated Use MergeCleanupCanonicalResponse */
export type MergeCleanupLocationCanonicalResponse = MergeCleanupCanonicalResponse

function mergeCleanupCanonicalPath(
  stylebookSlug: string,
  entitySegment: string,
  sourceCanonicalId: string,
): string {
  return `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/cleanup/${entitySegment}/${encodeURIComponent(sourceCanonicalId)}/merge-into`
}

function deleteEmptyCleanupCanonicalPath(
  stylebookSlug: string,
  entitySegment: string,
  canonicalId: string,
): string {
  return `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/cleanup/${entitySegment}/${encodeURIComponent(canonicalId)}`
}

async function mergeCleanupCanonical(
  stylebookSlug: string,
  entitySegment: string,
  sourceCanonicalId: string,
  targetCanonicalId: string,
): Promise<MergeCleanupCanonicalResponse> {
  return stylebookJsonFetch<MergeCleanupCanonicalResponse>(
    mergeCleanupCanonicalPath(stylebookSlug, entitySegment, sourceCanonicalId),
    {
      method: "POST",
      body: JSON.stringify({ target_canonical_id: targetCanonicalId }),
    },
  )
}

async function deleteEmptyCleanupCanonical(
  stylebookSlug: string,
  entitySegment: string,
  canonicalId: string,
): Promise<{ id: string; message: string }> {
  return stylebookJsonFetch(
    deleteEmptyCleanupCanonicalPath(stylebookSlug, entitySegment, canonicalId),
    { method: "DELETE" },
  )
}

export async function mergeCleanupLocationCanonical(
  stylebookSlug: string,
  sourceCanonicalId: string,
  targetCanonicalId: string,
): Promise<MergeCleanupCanonicalResponse> {
  return mergeCleanupCanonical(
    stylebookSlug,
    "canonical-locations",
    sourceCanonicalId,
    targetCanonicalId,
  )
}

export async function mergeCleanupPersonCanonical(
  stylebookSlug: string,
  sourceCanonicalId: string,
  targetCanonicalId: string,
): Promise<MergeCleanupCanonicalResponse> {
  return mergeCleanupCanonical(
    stylebookSlug,
    "canonical-people",
    sourceCanonicalId,
    targetCanonicalId,
  )
}

export async function mergeCleanupOrganizationCanonical(
  stylebookSlug: string,
  sourceCanonicalId: string,
  targetCanonicalId: string,
): Promise<MergeCleanupCanonicalResponse> {
  return mergeCleanupCanonical(
    stylebookSlug,
    "canonical-organizations",
    sourceCanonicalId,
    targetCanonicalId,
  )
}

export async function deleteEmptyCleanupLocationCanonical(
  stylebookSlug: string,
  canonicalId: string,
): Promise<{ id: string; message: string }> {
  return deleteEmptyCleanupCanonical(stylebookSlug, "canonical-locations", canonicalId)
}

export async function deleteEmptyCleanupPersonCanonical(
  stylebookSlug: string,
  canonicalId: string,
): Promise<{ id: string; message: string }> {
  return deleteEmptyCleanupCanonical(stylebookSlug, "canonical-people", canonicalId)
}

export async function deleteEmptyCleanupOrganizationCanonical(
  stylebookSlug: string,
  canonicalId: string,
): Promise<{ id: string; message: string }> {
  return deleteEmptyCleanupCanonical(stylebookSlug, "canonical-organizations", canonicalId)
}
