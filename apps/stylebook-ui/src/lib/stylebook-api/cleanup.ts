import { stylebookJsonFetch } from "@/lib/stylebook-api/client"

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

export interface CreateCleanupDismissalParams {
  stylebookSlug: string
  checkId: string
  memberIds?: string[]
  canonicalId?: string
}

export interface CleanupDismissalResponse {
  check_id: string
  dismissed_pair_count: number
  dismissed_canonical_id?: string | null
  message: string
}

export async function dismissCleanupIssue(
  params: CreateCleanupDismissalParams,
): Promise<CleanupDismissalResponse> {
  const body: Record<string, unknown> = { check_id: params.checkId }
  if (params.memberIds?.length) {
    body.member_ids = params.memberIds
  }
  if (params.canonicalId) {
    body.canonical_id = params.canonicalId
  }
  return stylebookJsonFetch<CleanupDismissalResponse>(
    `/v1/stylebooks/${encodeURIComponent(params.stylebookSlug)}/cleanup/dismissals`,
    {
      method: "POST",
      body: JSON.stringify(body),
    },
  )
}

export interface CleanupAiModel {
  id: string
  name: string
  provider_model_id: string
}

export interface CleanupAiModelsResponse {
  models: CleanupAiModel[]
}

export interface CleanupAiReview {
  id: string
  stylebook_id: number
  check_id: string
  status: string
  provider_model_id: string
  ai_model_config_id?: string | null
  cluster_count: number
  processed_cluster_count: number
  proposal_count: number
  error_message?: string | null
  created_at: string
  updated_at: string
}

export type CleanupAiProposalAction = "merge" | "keep_separate"

export interface CleanupAiProposal {
  id: string
  review_id: string
  check_id: string
  cluster_id: string
  action: CleanupAiProposalAction
  target_canonical_id?: string | null
  member_ids: string[]
  confidence: number
  rationale?: string | null
  status: string
}

export interface CleanupAiProposalsResponse {
  proposals: CleanupAiProposal[]
}

export interface CleanupAiProposalActionResponse {
  id: string
  status: string
  message: string
}

function cleanupAiReviewPath(stylebookSlug: string, reviewId?: string): string {
  const base = `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/cleanup/ai-review`
  return reviewId ? `${base}/${encodeURIComponent(reviewId)}` : base
}

export async function listCleanupAiModels(stylebookSlug: string): Promise<CleanupAiModelsResponse> {
  return stylebookJsonFetch<CleanupAiModelsResponse>(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/cleanup/ai-models`,
  )
}

export async function startCleanupAiReview(params: {
  stylebookSlug: string
  checkId: string
  providerModelId: string
  aiModelConfigId?: string | null
}): Promise<CleanupAiReview> {
  return stylebookJsonFetch<CleanupAiReview>(cleanupAiReviewPath(params.stylebookSlug), {
    method: "POST",
    body: JSON.stringify({
      check_id: params.checkId,
      provider_model_id: params.providerModelId,
      ai_model_config_id: params.aiModelConfigId ?? null,
    }),
  })
}

export async function getCleanupAiReview(
  stylebookSlug: string,
  reviewId: string,
): Promise<CleanupAiReview> {
  return stylebookJsonFetch<CleanupAiReview>(cleanupAiReviewPath(stylebookSlug, reviewId))
}

export async function getLatestCleanupAiReview(
  stylebookSlug: string,
  checkId: string,
): Promise<CleanupAiReview | null> {
  const q = new URLSearchParams({ check_id: checkId })
  return stylebookJsonFetch<CleanupAiReview | null>(
    `${cleanupAiReviewPath(stylebookSlug)}/latest?${q.toString()}`,
  )
}

export async function cancelCleanupAiReview(
  stylebookSlug: string,
  reviewId: string,
): Promise<CleanupAiReview> {
  return stylebookJsonFetch<CleanupAiReview>(
    `${cleanupAiReviewPath(stylebookSlug, reviewId)}/cancel`,
    { method: "POST" },
  )
}

export async function listCleanupAiProposals(params: {
  stylebookSlug: string
  reviewId: string
  status?: string
}): Promise<CleanupAiProposalsResponse> {
  const q = new URLSearchParams()
  if (params.status) q.set("status", params.status)
  const suffix = q.toString() ? `?${q.toString()}` : ""
  return stylebookJsonFetch<CleanupAiProposalsResponse>(
    `${cleanupAiReviewPath(params.stylebookSlug, params.reviewId)}/proposals${suffix}`,
  )
}

export async function acceptCleanupAiProposal(params: {
  stylebookSlug: string
  proposalId: string
}): Promise<CleanupAiProposalActionResponse> {
  return stylebookJsonFetch<CleanupAiProposalActionResponse>(
    `/v1/stylebooks/${encodeURIComponent(params.stylebookSlug)}/cleanup/ai-review/proposals/${encodeURIComponent(params.proposalId)}/accept`,
    { method: "POST" },
  )
}

export async function rejectCleanupAiProposal(params: {
  stylebookSlug: string
  proposalId: string
}): Promise<CleanupAiProposalActionResponse> {
  return stylebookJsonFetch<CleanupAiProposalActionResponse>(
    `/v1/stylebooks/${encodeURIComponent(params.stylebookSlug)}/cleanup/ai-review/proposals/${encodeURIComponent(params.proposalId)}/reject`,
    { method: "POST" },
  )
}
