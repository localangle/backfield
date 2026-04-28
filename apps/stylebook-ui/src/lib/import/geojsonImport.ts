export type GeoJsonGeometry = Record<string, unknown>

export type GeoJsonFeature = {
  type?: string
  geometry?: GeoJsonGeometry | null
  properties?: Record<string, unknown> | null
}

export type GeoJsonFeatureCollection = {
  type: "FeatureCollection"
  features: GeoJsonFeature[]
}

export type GeoJsonFieldMappings = {
  /** Feature.properties key for label/name. */
  labelProperty?: string | null
  /** Feature.properties key for location_type. */
  locationTypeProperty?: string | null
  /** Feature.properties key for formatted_address. */
  formattedAddressProperty?: string | null
  /** When set, overrides all per-feature type values. */
  locationTypeValue?: string | null
}

export type DerivedImportRow = {
  feature_index: number
  label: string | null
  location_type: string | null
  formatted_address: string | null
  geometry_type: string | null
  has_geometry: boolean
}

export type ReviewEditsByFeatureIndex = Record<
  number,
  Partial<Pick<DerivedImportRow, "label" | "location_type" | "formatted_address">>
>

export type ImportValidationSummary = {
  total_rows: number
  missing_label_count: number
  missing_location_type_count: number
  missing_geometry_count: number
}

function _getStringProp(props: Record<string, unknown> | null | undefined, key: string | null | undefined): string | null {
  if (!props || !key) return null
  const v = props[key]
  if (v == null) return null
  const s = String(v).trim()
  return s ? s : null
}

function _getGeometryType(geom: GeoJsonGeometry | null | undefined): string | null {
  if (!geom || typeof geom !== "object") return null
  const t = (geom as Record<string, unknown>).type
  if (t == null) return null
  const s = String(t).trim()
  return s ? s : null
}

export function deriveImportRows(
  fc: GeoJsonFeatureCollection,
  mappings: GeoJsonFieldMappings,
): DerivedImportRow[] {
  const out: DerivedImportRow[] = []
  const typeOverride = (mappings.locationTypeValue ?? "").trim() || null

  for (let i = 0; i < fc.features.length; i++) {
    const f = fc.features[i] ?? {}
    const props = (f.properties && typeof f.properties === "object" ? f.properties : null) as
      | Record<string, unknown>
      | null
    const geom = (f.geometry && typeof f.geometry === "object" ? f.geometry : null) as GeoJsonGeometry | null
    const geometryType = _getGeometryType(geom)

    const label = _getStringProp(props, mappings.labelProperty) ?? null
    const locationType =
      typeOverride ??
      _getStringProp(props, mappings.locationTypeProperty) ??
      null
    const formattedAddress = _getStringProp(props, mappings.formattedAddressProperty) ?? null

    out.push({
      feature_index: i,
      label,
      location_type: locationType,
      formatted_address: formattedAddress,
      geometry_type: geometryType,
      has_geometry: Boolean(geometryType),
    })
  }

  return out
}

export function validateDerivedRows(rows: DerivedImportRow[]): ImportValidationSummary {
  let missingLabel = 0
  let missingType = 0
  let missingGeom = 0

  for (const r of rows) {
    if (!r.label) missingLabel++
    if (!r.location_type) missingType++
    if (!r.has_geometry) missingGeom++
  }

  return {
    total_rows: rows.length,
    missing_label_count: missingLabel,
    missing_location_type_count: missingType,
    missing_geometry_count: missingGeom,
  }
}

export function canProceedFromMapping(summary: ImportValidationSummary): boolean {
  return (
    summary.total_rows > 0 &&
    summary.missing_label_count === 0 &&
    summary.missing_location_type_count === 0 &&
    summary.missing_geometry_count === 0
  )
}

function _upsertStringProp(
  props: Record<string, unknown>,
  key: string,
  value: string | null | undefined,
): void {
  if (value == null) return
  const v = String(value).trim()
  if (!v) return
  props[key] = v
}

/**
 * Build a submission FeatureCollection for the import endpoint.
 *
 * This is intentionally simple: we keep geometry unchanged and write edited fields back into
 * `feature.properties` so the backend can apply the existing field mapping/fallback logic.
 */
export function buildFeatureCollectionForImport(
  fc: GeoJsonFeatureCollection,
  mappings: GeoJsonFieldMappings,
  editsByFeatureIndex: ReviewEditsByFeatureIndex,
  excludedFeatureIndices: Set<number>,
): GeoJsonFeatureCollection {
  const outFeatures: GeoJsonFeature[] = []

  const nameKey = mappings.labelProperty || "name"
  const typeKey = mappings.locationTypeProperty || "type"
  const addressKey = mappings.formattedAddressProperty || "formatted_address"

  const typeOverride = (mappings.locationTypeValue ?? "").trim() || null

  for (let i = 0; i < fc.features.length; i++) {
    if (excludedFeatureIndices.has(i)) continue
    const f = fc.features[i]
    if (!f || typeof f !== "object") continue

    const baseProps =
      f.properties && typeof f.properties === "object"
        ? (f.properties as Record<string, unknown>)
        : {}
    const nextProps: Record<string, unknown> = { ...baseProps }

    const edits = editsByFeatureIndex[i] || {}
    _upsertStringProp(nextProps, nameKey, edits.label ?? null)
    _upsertStringProp(nextProps, addressKey, edits.formatted_address ?? null)
    if (typeOverride) {
      _upsertStringProp(nextProps, typeKey, typeOverride)
    } else {
      _upsertStringProp(nextProps, typeKey, edits.location_type ?? null)
    }

    outFeatures.push({
      ...f,
      properties: nextProps,
    })
  }

  return {
    type: "FeatureCollection",
    features: outFeatures,
  }
}

