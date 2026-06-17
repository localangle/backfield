/**
 * Frontend registry for Stylebook cleanup checks (hub navigation + copy).
 * Counts come from the API; ids must match backfield_entities.quality.checks.
 */

export type CleanupCheckKind = "cluster" | "list"

export interface CleanupCheckConfig {
  id: string
  title: string
  description: string
  kind: CleanupCheckKind
}

export const CLEANUP_CHECK_CONFIGS: CleanupCheckConfig[] = [
  {
    id: "duplicate-locations",
    title: "Possible duplicate locations",
    description:
      "Groups of location names that look very similar. Open each record to compare and relink evidence.",
    kind: "cluster",
  },
  {
    id: "missing-geometry-locations",
    title: "Locations missing geography",
    description:
      "Location records with no map pin or shape. Open each record to add geography.",
    kind: "list",
  },
]

export function cleanupCheckConfigById(checkId: string): CleanupCheckConfig | undefined {
  return CLEANUP_CHECK_CONFIGS.find((check) => check.id === checkId)
}
