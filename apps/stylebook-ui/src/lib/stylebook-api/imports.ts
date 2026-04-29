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

export type ImportGeoJsonMappings = {
  label_property?: string | null
  location_type_property?: string | null
  formatted_address_property?: string | null
  location_type_value?: string | null
}

export type ImportGeoJsonRequest = {
  geojson: GeoJsonFeatureCollection | Record<string, unknown>
  mappings: ImportGeoJsonMappings
}

export type ImportGeoJsonResponse = {
  total_features: number
  attempted_features: number
  created_count: number
  failed_count: number
  created: { feature_index: number; canonical_id: string; label: string }[]
  failed: { feature_index: number; error: string }[]
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

export async function importGeoJson(
  projectSlug: string,
  geojson: Record<string, unknown>,
  mappings: ImportGeoJsonMappings,
): Promise<ImportGeoJsonResponse> {
  const params = new URLSearchParams({ project_slug: projectSlug })
  return stylebookJsonFetch<ImportGeoJsonResponse>(`/v1/import/geojson?${params}`, {
    method: "POST",
    body: JSON.stringify({ geojson, mappings } satisfies ImportGeoJsonRequest),
  })
}

