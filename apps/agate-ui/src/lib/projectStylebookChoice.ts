/**
 * Choosing a Stylebook while creating a project.
 *
 * A project's Stylebook is fixed when the project is created. The workspace supplies the
 * default, and the person creating the project may pick a different Stylebook from the
 * same organization. Most organizations have exactly one Stylebook and never see a choice.
 */

/** Minimal shape the dialog needs from an organization's Stylebook list. */
export interface StylebookOption {
  id: number
  name: string
}

export interface StylebookSelectionInput {
  stylebooks: StylebookOption[]
  /** Default from the workspace currently selected in the dialog. */
  workspaceStylebookId: number | null
  /** Set once the person creating the project picks a Stylebook themselves. */
  chosenStylebookId: number | null
}

export function shouldOfferStylebookChoice(stylebooks: StylebookOption[]): boolean {
  return stylebooks.length > 1
}

/**
 * The Stylebook the dialog shows as selected.
 *
 * An explicit pick wins and survives a workspace change, so the choice is never silently
 * undone. Without a pick, the selection follows the workspace default. Values that are not
 * in the organization's list (stale pick, unreadable workspace) fall back to the first
 * Stylebook so the control is never blank.
 */
export function resolveStylebookSelection({
  stylebooks,
  workspaceStylebookId,
  chosenStylebookId,
}: StylebookSelectionInput): number | null {
  const available = new Set(stylebooks.map((s) => s.id))
  if (chosenStylebookId != null && available.has(chosenStylebookId)) {
    return chosenStylebookId
  }
  if (workspaceStylebookId != null && available.has(workspaceStylebookId)) {
    return workspaceStylebookId
  }
  return stylebooks[0]?.id ?? null
}

/**
 * Value to send with a create request, or `null` to omit the field.
 *
 * Only a deliberate pick is sent. The displayed default is a hint drawn from data the client
 * may have fetched a while ago, so sending it back would pin a possibly stale workspace
 * default instead of the one the server resolves at creation time.
 */
export function stylebookIdForCreate({
  stylebooks,
  chosenStylebookId,
}: StylebookSelectionInput): number | null {
  if (chosenStylebookId == null) return null
  return stylebooks.some((s) => s.id === chosenStylebookId) ? chosenStylebookId : null
}
