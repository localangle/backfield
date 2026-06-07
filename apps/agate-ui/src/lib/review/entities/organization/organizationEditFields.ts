/** Read/write organization fields during Agate organizations review. */

import type { MentionOccurrenceDraft } from '../location/mentionOccurrences'
import {
  buildOccurrencesOverlayPayload,
  mentionOccurrencesEqual,
  primaryMentionText,
  readMentionOccurrencesFromRow,
} from '../location/mentionOccurrences'

export type OrganizationEditFields = {
  name: string
  organizationType: string
  roleInStory: string
  nature: string
  natureSecondaryTags: string[]
  occurrences: MentionOccurrenceDraft[]
}

function cloneJson<T>(v: T): T {
  return JSON.parse(JSON.stringify(v)) as T
}

export function readOrganizationEditFields(
  organization: Record<string, unknown> | null | undefined,
  row?: { mention_occurrences?: unknown; organization?: Record<string, unknown> },
): OrganizationEditFields {
  if (!organization || typeof organization !== 'object') {
    return {
      name: '',
      organizationType: '',
      roleInStory: '',
      nature: '',
      natureSecondaryTags: [],
      occurrences: [],
    }
  }
  const name = typeof organization.name === 'string' ? organization.name.trim() : ''
  const occurrences = readMentionOccurrencesFromRow({
    location: organization,
    mention_occurrences: row?.mention_occurrences,
  })
  const tagsRaw = organization.nature_secondary_tags
  const natureSecondaryTags = Array.isArray(tagsRaw)
    ? tagsRaw.filter((t): t is string => typeof t === 'string' && t.trim().length > 0)
    : []
  return {
    name,
    organizationType: typeof organization.type === 'string' ? organization.type.trim() : '',
    roleInStory:
      typeof organization.role_in_story === 'string' ? organization.role_in_story.trim() : '',
    nature: typeof organization.nature === 'string' ? organization.nature.trim() : '',
    natureSecondaryTags,
    occurrences,
  }
}

export function organizationEditFieldsEqual(
  a: OrganizationEditFields,
  b: OrganizationEditFields,
): boolean {
  return (
    a.name === b.name &&
    a.organizationType === b.organizationType &&
    a.roleInStory === b.roleInStory &&
    a.nature === b.nature &&
    a.natureSecondaryTags.join('\0') === b.natureSecondaryTags.join('\0') &&
    mentionOccurrencesEqual(a.occurrences, b.occurrences)
  )
}

export function applyOrganizationEditFields(
  organization: Record<string, unknown>,
  fields: OrganizationEditFields,
): Record<string, unknown> {
  const out = cloneJson(organization) as Record<string, unknown>
  out.name = fields.name.trim()
  out.type = fields.organizationType.trim()
  out.role_in_story = fields.roleInStory.trim()
  out.nature = fields.nature.trim()
  out.nature_secondary_tags = fields.natureSecondaryTags.map((t) => t.trim()).filter(Boolean)
  const primary = primaryMentionText(fields.occurrences)
  if (primary) {
    out.original_text = primary
  }
  out.mentions = fields.occurrences
    .filter((o) => !o.suppressed && o.mentionText.trim())
    .map((o) => ({
      text: o.mentionText.trim(),
      quote: Boolean(o.isQuote),
    }))
  return out
}

export function buildOrganizationEditOverlayPatch(
  fields: OrganizationEditFields,
): Record<string, unknown> {
  return {
    name: fields.name.trim(),
    type: fields.organizationType.trim(),
    role_in_story: fields.roleInStory.trim(),
    nature: fields.nature.trim(),
    nature_secondary_tags: fields.natureSecondaryTags.map((t) => t.trim()).filter(Boolean),
    occurrences: buildOccurrencesOverlayPayload(fields.occurrences),
  }
}
