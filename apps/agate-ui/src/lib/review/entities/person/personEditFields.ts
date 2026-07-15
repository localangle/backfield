/** Read/write person fields during Agate people review. */

import type { MentionOccurrenceDraft } from '../location/mentionOccurrences'
import {
  buildOccurrencesOverlayPayload,
  mentionOccurrencesEqual,
  primaryMentionText,
  readMentionOccurrencesFromRow,
} from '../location/mentionOccurrences'

export type PersonEditFields = {
  name: string
  title: string
  affiliation: string
  personType: string
  roleInStory: string
  nature: string
  publicFigure: boolean
  sortKey: string
  occurrences: MentionOccurrenceDraft[]
}

function cloneJson<T>(v: T): T {
  return JSON.parse(JSON.stringify(v)) as T
}

/** Derive lowercase last-name sort key from a display name. */
export function derivePersonSortKey(name: string, explicit?: string | null): string | null {
  const norm = (v: string) => {
    const cleaned = v.trim().toLowerCase().replace(/\s+/g, ' ')
    return cleaned || null
  }
  const fromExplicit = explicit != null ? norm(explicit) : null
  if (fromExplicit) return fromExplicit
  const trimmed = name.trim()
  if (!trimmed) return null
  const parts = trimmed.split(/\s+/)
  if (parts.length >= 2) return norm(parts[parts.length - 1]!)
  return norm(parts[0]!)
}

export function readPersonEditFields(
  person: Record<string, unknown> | null | undefined,
  row?: { mention_occurrences?: unknown; person?: Record<string, unknown> },
): PersonEditFields {
  if (!person || typeof person !== 'object') {
    return {
      name: '',
      title: '',
      affiliation: '',
      personType: '',
      roleInStory: '',
      nature: '',
      publicFigure: false,
      sortKey: '',
      occurrences: [],
    }
  }
  const name = typeof person.name === 'string' ? person.name.trim() : ''
  const occurrences = readMentionOccurrencesFromRow({
    location: person,
    mention_occurrences: row?.mention_occurrences,
  })
  const explicitSortKey =
    typeof person.sort_key === 'string' ? person.sort_key.trim().toLowerCase() : ''
  return {
    name,
    title: typeof person.title === 'string' ? person.title.trim() : '',
    affiliation: typeof person.affiliation === 'string' ? person.affiliation.trim() : '',
    personType: typeof person.type === 'string' ? person.type.trim() : '',
    roleInStory: typeof person.role_in_story === 'string' ? person.role_in_story.trim() : '',
    nature: typeof person.nature === 'string' ? person.nature.trim() : '',
    publicFigure: Boolean(person.public_figure),
    sortKey: explicitSortKey || derivePersonSortKey(name) || '',
    occurrences,
  }
}

export function personEditFieldsEqual(a: PersonEditFields, b: PersonEditFields): boolean {
  return (
    a.name === b.name &&
    a.title === b.title &&
    a.affiliation === b.affiliation &&
    a.personType === b.personType &&
    a.roleInStory === b.roleInStory &&
    a.nature === b.nature &&
    a.publicFigure === b.publicFigure &&
    a.sortKey === b.sortKey &&
    mentionOccurrencesEqual(a.occurrences, b.occurrences)
  )
}

export function applyPersonEditFields(
  person: Record<string, unknown>,
  fields: PersonEditFields,
): Record<string, unknown> {
  const out = cloneJson(person) as Record<string, unknown>
  out.name = fields.name.trim()
  out.title = fields.title.trim()
  out.affiliation = fields.affiliation.trim()
  out.type = fields.personType.trim()
  out.role_in_story = fields.roleInStory.trim()
  out.nature = fields.nature.trim()
  out.public_figure = fields.publicFigure
  out.sort_key = derivePersonSortKey(fields.name, fields.sortKey || null)
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

export function buildPersonEditOverlayPatch(fields: PersonEditFields): Record<string, unknown> {
  return {
    name: fields.name.trim(),
    title: fields.title.trim(),
    affiliation: fields.affiliation.trim(),
    type: fields.personType.trim(),
    role_in_story: fields.roleInStory.trim(),
    nature: fields.nature.trim(),
    public_figure: fields.publicFigure,
    sort_key: derivePersonSortKey(fields.name, fields.sortKey || null),
    occurrences: buildOccurrencesOverlayPayload(fields.occurrences),
  }
}
