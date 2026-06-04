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

export type ImportGeoJsonMetaPropertyMapping = {
  meta_type: string
  property_key: string
}

export type ImportGeoJsonRequest = {
  geojson: GeoJsonFeatureCollection | Record<string, unknown>
  mappings: ImportGeoJsonMappings
  meta_property_mappings?: ImportGeoJsonMetaPropertyMapping[]
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
  stylebookSlug: string,
  geojson: Record<string, unknown>,
): Promise<AnalyzeGeoJsonResponse> {
  return stylebookJsonFetch<AnalyzeGeoJsonResponse>(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/import/geojson/analyze`,
    {
    method: "POST",
    body: JSON.stringify({ geojson } satisfies AnalyzeGeoJsonRequest),
    },
  )
}

export async function importGeoJson(
  stylebookSlug: string,
  geojson: Record<string, unknown>,
  mappings: ImportGeoJsonMappings,
  meta_property_mappings?: ImportGeoJsonMetaPropertyMapping[],
): Promise<ImportGeoJsonResponse> {
  const body: ImportGeoJsonRequest = {
    geojson,
    mappings,
    meta_property_mappings: meta_property_mappings?.length ? meta_property_mappings : [],
  }
  return stylebookJsonFetch<ImportGeoJsonResponse>(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/import/geojson`,
    { method: "POST", body: JSON.stringify(body) },
  )
}

export type AnalyzeCsvResponse = {
  row_count: number
  available_columns: string[]
  sample_row: Record<string, string> | null
}

export type PersonCsvFieldMappings = {
  label?: string
  full_name?: string
  first_name?: string
  last_name?: string
  title?: string
  affiliation?: string
  public_figure?: string
  person_type?: string
  sort_key?: string
}

export type ImportCsvResponse = {
  total_rows: number
  attempted_rows: number
  created_count: number
  failed_count: number
  created: { row_index: number; canonical_id: string; label: string }[]
  failed: { row_index: number; error: string }[]
}

export async function analyzeImportCsvPeople(
  stylebookSlug: string,
  csvData: string,
): Promise<AnalyzeCsvResponse> {
  return stylebookJsonFetch<AnalyzeCsvResponse>(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/import/csv/people/analyze`,
    {
      method: "POST",
      body: JSON.stringify({ csv_data: csvData }),
    },
  )
}

export async function importCsvPeople(
  stylebookSlug: string,
  csvData: string,
  fieldMappings?: PersonCsvFieldMappings,
): Promise<ImportCsvResponse> {
  const mappings: Record<string, string> = {}
  if (fieldMappings) {
    for (const [key, col] of Object.entries(fieldMappings)) {
      if (col && col.trim()) mappings[key] = col.trim()
    }
  }
  return stylebookJsonFetch<ImportCsvResponse>(
    `/v1/stylebooks/${encodeURIComponent(stylebookSlug)}/import/csv/people`,
    {
      method: "POST",
      body: JSON.stringify({ csv_data: csvData, field_mappings: mappings }),
    },
  )
}

