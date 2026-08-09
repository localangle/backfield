/**
 * The Stylebook a project reads and writes.
 *
 * A project owns its Stylebook directly from the moment it is created. Its workspace only
 * supplies the default offered at creation, so the two diverge whenever a project was created
 * with an explicit choice. Anything that reads or writes catalog data for a project must use
 * the project's own Stylebook.
 */

import type { Project } from '@/lib/api'

/**
 * Stylebook slug that story review reads, writes, and deep-links into.
 *
 * Never substitute `workspace_stylebook_slug`: that reports the workspace's current default and
 * would send edits into the wrong Stylebook.
 */
export function reviewStylebookSlug(project: Project | null | undefined): string | null {
  return project?.stylebook_slug?.trim() || null
}

/** Name shown under the project title for the Stylebook a project writes into. */
export function projectStylebookDisplayName(project: Pick<Project, 'stylebook_name'>): string {
  return project.stylebook_name?.trim() || 'Not available'
}
