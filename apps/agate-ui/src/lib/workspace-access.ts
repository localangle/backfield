import type { WorkspaceWithProjects } from "@/lib/core-api"

/** Org admins always qualify; members need at least one real workspace (not synthetic `_ungrouped`). */
export function hasWorkspaceAccess(
  rows: WorkspaceWithProjects[],
  isOrgAdmin: boolean,
): boolean {
  if (isOrgAdmin) return true
  return rows.some((ws) => ws.id > 0 && ws.slug !== "_ungrouped")
}
