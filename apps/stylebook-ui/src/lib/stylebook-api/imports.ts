import { stylebookJsonFetch } from "@/lib/stylebook-api/client"

export type GeoJsonFeatureCollection = {
  type: "FeatureCollection"
  features: unknown[]
}

export type AnalyzeGeoJsonRequest = {
  geojson: GeoJsonFeatureCollection | Record<string, unknown>
}

export type AnalyzeGeoJsonResponse = {
  feature_count: number
  available_properties: string[]
  sample_feature: { properties: Record<string, unknown>; geometry_type?: string | null } | null
}

export async function analyzeImportGeoJson(
  projectSlug: string,
  geojson: Record<string, unknown>,
): Promise<AnalyzeGeoJsonResponse> {
  const params = new URLSearchParams({ project_slug: projectSlug })
  return stylebookJsonFetch<AnalyzeGeoJsonResponse>(`/v1/import/geojson/analyze?${params}`, {
    method: "POST",
    body: JSON.stringify({ geojson } satisfies AnalyzeGeoJsonRequest),
  })
}

