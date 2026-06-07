/**
 * Mirror of ``backfield_entities.entities.person.types.PERSON_TYPE_VALUES``.
 * Keep in sync when the PersonExtract taxonomy changes.
 */
export const PERSON_EXTRACT_PERSON_TYPES = [
  "athlete",
  "coach",
  "sports_official",
  "sports_executive",
  "elected_official",
  "government_official",
  "political_staff",
  "lawyer_legal_advocate",
  "judge_court_official",
  "law_enforcement_public_safety",
  "crime_justice_subject",
  "business_owner_executive",
  "business_professional",
  "labor_union_representative",
  "artist_entertainer",
  "media_journalism",
  "arts_culture_professional",
  "education_research_expert",
  "healthcare_worker",
  "community_member",
  "unknown",
  "other",
] as const

/** Explicit labels for PersonExtract ``type`` values used in review UI. */
const PERSON_TYPE_LABEL_OVERRIDES: Record<string, string> = {
  law_enforcement_public_safety: "Law enforcement / public safety",
  crime_justice_subject: "Crime / justice subject",
  business_owner_executive: "Business owner / executive",
  labor_union_representative: "Labor / union representative",
  arts_culture_professional: "Arts / culture professional",
  education_research_expert: "Education / research expert",
  lawyer_legal_advocate: "Lawyer / legal advocate",
  judge_court_official: "Judge / court official",
  media_journalism: "Media / journalism",
}

/**
 * Mirror of ``backfield_entities.entities.location.types.PLACE_EXTRACT_LOCATION_TYPES``.
 * Keep in sync when the PlaceExtract taxonomy changes.
 */
export const PLACE_EXTRACT_LOCATION_TYPES = [
  "place",
  "address",
  "intersection_road",
  "intersection_highway",
  "street_road",
  "span",
  "political_district",
  "neighborhood",
  "region_city",
  "city",
  "county",
  "region_state",
  "state",
  "region_national",
  "country",
  "natural",
  "other",
] as const

/** Explicit labels for PlaceExtract ``location.type`` values used in the review queue UI. */
const TYPE_LABEL_OVERRIDES: Record<string, string> = {
  region_city: "Region (City)",
  region_national: "Region (National)",
  region_state: "Region (State)",
  intersection_road: "Intersection (Road)",
  intersection_highway: "Intersection (Highway)",
  street_road: "Street/Road",
  political_district: "Political district",
}

/** Human label for a PlaceExtract or PersonExtract type slug (snake_case → Title Case, with overrides). */
export function placeExtractTypeLabel(value: string): string {
  const raw = value.trim()
  if (!raw) return value
  const key = raw.toLowerCase()
  const personMapped = PERSON_TYPE_LABEL_OVERRIDES[key]
  if (personMapped) return personMapped
  const mapped = TYPE_LABEL_OVERRIDES[key]
  if (mapped) return mapped
  return raw
    .split("_")
    .map((part) => (part ? part.charAt(0).toUpperCase() + part.slice(1).toLowerCase() : ""))
    .filter(Boolean)
    .join(" ")
}

/**
 * Sort type filter values A–Z by display label; ``unknown`` and ``other`` (any casing) stay last.
 */
export function sortReviewQueueTypeFilterOptions(types: string[]): string[] {
  const list = types.filter((t) => String(t).trim() !== "")
  const trailing: string[] = []
  const rest: string[] = []
  for (const t of list) {
    const lower = t.toLowerCase()
    if (lower === "other" || lower === "unknown") trailing.push(t)
    else rest.push(t)
  }
  rest.sort((a, b) =>
    placeExtractTypeLabel(a).localeCompare(placeExtractTypeLabel(b), undefined, {
      sensitivity: "base",
    }),
  )
  return [...rest, ...trailing]
}

/** Options for manual person-type pickers (taxonomy only, plus legacy current value when editing). */
export function personTypeManualSelectOptions(current?: string | null): string[] {
  const taxonomy = sortReviewQueueTypeFilterOptions([...PERSON_EXTRACT_PERSON_TYPES])
  const cur = (current ?? "").trim()
  if (cur && !taxonomy.includes(cur)) {
    return [...taxonomy, cur]
  }
  return taxonomy
}

/**
 * Mirror of ``backfield_entities.entities.organization.types.ORGANIZATION_TYPE_VALUES``.
 * Keep in sync when the OrganizationExtract taxonomy changes.
 */
export const ORGANIZATION_EXTRACT_ORGANIZATION_TYPES = [
  "government",
  "law_enforcement",
  "court",
  "legislative_body",
  "political_party",
  "school_district",
  "school",
  "university",
  "hospital",
  "public_health",
  "public_services",
  "utilities",
  "company",
  "local_business",
  "financial_institution",
  "real_estate",
  "nonprofit",
  "community_group",
  "religious_org",
  "culture_arts",
  "sports_team",
  "sports_league",
  "media",
  "other",
] as const

/** Options for manual organization-type pickers (taxonomy only, plus legacy current value when editing). */
export function organizationTypeManualSelectOptions(current?: string | null): string[] {
  const taxonomy = sortReviewQueueTypeFilterOptions([...ORGANIZATION_EXTRACT_ORGANIZATION_TYPES])
  const cur = (current ?? "").trim()
  if (cur && !taxonomy.includes(cur)) {
    return [...taxonomy, cur]
  }
  return taxonomy
}
