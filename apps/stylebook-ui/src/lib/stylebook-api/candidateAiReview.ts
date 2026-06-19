import { stylebookJsonFetch } from "@/lib/stylebook-api/client"

export type CandidateAiReviewEntityType = "person" | "organization" | "location"

export interface CandidateAiModel {
  id: string
  name: string
  provider_model_id: string
}

export interface CandidateAiModelsResponse {
  models: CandidateAiModel[]
}

export interface CandidateAiReview {
  id: string
  stylebook_id: number
  project_id: number
  entity_type: string
  status: string
  provider_model_id: string
  ai_model_config_id?: string | null
  candidate_count: number
  processed_count: number
  recommendation_count: number
  error_message?: string | null
  created_at: string
  updated_at: string
}

export async function listCandidateAiModels(stylebookSlug: string): Promise<CandidateAiModelsResponse> {
  return stylebookJsonFetch<CandidateAiModelsResponse>(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/candidates/ai-models`,
  )
}

export async function startCandidateAiReview(params: {
  stylebookSlug: string
  entityType: CandidateAiReviewEntityType
  projectSlug: string
  providerModelId: string
  aiModelConfigId: string
}): Promise<CandidateAiReview> {
  return stylebookJsonFetch<CandidateAiReview>(
    `/v1/stylebooks/${encodeURIComponent(params.stylebookSlug)}/candidates/ai-review`,
    {
      method: "POST",
      body: JSON.stringify({
        entity_type: params.entityType,
        project_slug: params.projectSlug,
        provider_model_id: params.providerModelId,
        ai_model_config_id: params.aiModelConfigId,
      }),
    },
  )
}

export async function getLatestCandidateAiReview(
  stylebookSlug: string,
  entityType: CandidateAiReviewEntityType,
  projectSlug: string,
): Promise<CandidateAiReview | null> {
  const qs = new URLSearchParams({
    entity_type: entityType,
    project_slug: projectSlug,
  })
  return stylebookJsonFetch<CandidateAiReview | null>(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/candidates/ai-review/latest?${qs}`,
  )
}

export async function getCandidateAiReview(
  stylebookSlug: string,
  reviewId: string,
): Promise<CandidateAiReview> {
  return stylebookJsonFetch<CandidateAiReview>(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/candidates/ai-review/${encodeURIComponent(reviewId)}`,
  )
}
