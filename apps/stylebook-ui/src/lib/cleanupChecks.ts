/**
 * Frontend registry for Stylebook cleanup checks (hub navigation + copy).
 * Counts come from the API; ids must match backfield_entities.quality.checks.
 */

export type CleanupCheckKind = "cluster" | "list"
export type CleanupEntityType = "location" | "person" | "organization"

export interface CleanupCheckConfig {
  id: string
  title: string
  description: string
  kind: CleanupCheckKind
  entityType: CleanupEntityType
}

export const CLEANUP_CHECK_CONFIGS: CleanupCheckConfig[] = [
  {
    id: "duplicate-locations",
    title: "Possible duplicate locations",
    description:
      "Same or very similar location names. Open each record to compare and relink evidence.",
    kind: "cluster",
    entityType: "location",
  },
  {
    id: "missing-geometry-locations",
    title: "Missing or potentially incorrect geographies",
    description:
      "Records with no map geography, or linked places far from the catalog location. Open each record to review.",
    kind: "list",
    entityType: "location",
  },
  {
    id: "duplicate-people",
    title: "Possible duplicate people",
    description:
      "Same or very similar person names. Open each record to compare and relink evidence.",
    kind: "cluster",
    entityType: "person",
  },
  {
    id: "mismatched-people",
    title: "Possibly mismatched people",
    description:
      "People with linked mentions whose names look unlike this record. Open each record to review the link.",
    kind: "list",
    entityType: "person",
  },
  {
    id: "duplicate-organizations",
    title: "Possible duplicate organizations",
    description:
      "Same or very similar organization names. Open each record to compare and relink evidence.",
    kind: "cluster",
    entityType: "organization",
  },
  {
    id: "mismatched-organizations",
    title: "Possibly mismatched organizations",
    description:
      "Organizations with linked mentions whose names look unlike this record. Open each record to review the link.",
    kind: "list",
    entityType: "organization",
  },
]

export function cleanupCheckConfigById(checkId: string): CleanupCheckConfig | undefined {
  return CLEANUP_CHECK_CONFIGS.find((check) => check.id === checkId)
}

export function cleanupLinkedRecordLabel(entityType: CleanupEntityType): string {
  switch (entityType) {
    case "person":
      return "linked people"
    case "organization":
      return "linked organizations"
    default:
      return "linked places"
  }
}

export function cleanupLinkedRecordSingular(entityType: CleanupEntityType): string {
  switch (entityType) {
    case "person":
      return "linked person"
    case "organization":
      return "linked organization"
    default:
      return "linked place"
  }
}

export function cleanupEntityDetailPath(
  catalogBasePath: string,
  entityType: CleanupEntityType,
  canonicalId: string,
  scopeSuffix: string,
): string {
  const encoded = encodeURIComponent(canonicalId)
  switch (entityType) {
    case "person":
      return `${catalogBasePath}/people/canonical/${encoded}${scopeSuffix}`
    case "organization":
      return `${catalogBasePath}/organizations/canonical/${encoded}${scopeSuffix}`
    default:
      return `${catalogBasePath}/locations/canonical/${encoded}${scopeSuffix}`
  }
}
