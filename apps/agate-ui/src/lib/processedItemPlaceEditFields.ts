/**
 * Read/write core place fields during Review geometry edit (overlay + saved-place saves).
 */

import {
  applyGeometryToPlaceRow,
  applyOverlayPatchAfterGeometryAssignment,
  buildGeocodePatchForClearGeometry,
  buildGeocodePatchForFormattedAddress,
  buildGeocodePatchForGeometry,
  getGeocodedPlaceDisplay,
  readRoleInStoryFromPlace,
} from './processedItemPlaceGeometry'
import type { MentionOccurrenceDraft } from './processedItemMentionOccurrences'
import {
  buildOccurrencesOverlayPayload,
  mentionOccurrencesEqual,
  primaryMentionText,
  readMentionOccurrencesFromRow,
} from './processedItemMentionOccurrences'

export type PlaceEditFields = {
  label: string
  type: string
  formattedAddress: string
  roleInStory: string
  /** @deprecated Use ``occurrences``; kept for tests that only set mention text. */
  mentionText: string
  occurrences: MentionOccurrenceDraft[]
}

function cloneJson<T>(v: T): T {
  return JSON.parse(JSON.stringify(v)) as T
}

/** Read editable fields from a merged place row ``location`` object. */
export function readPlaceEditFields(
  place: Record<string, unknown> | null | undefined,
  row?: { mention_occurrences?: unknown; location?: Record<string, unknown> },
): PlaceEditFields {
  if (!place || typeof place !== 'object') {
    return { label: '', type: '', formattedAddress: '', roleInStory: '', mentionText: '', occurrences: [] }
  }
  const display = getGeocodedPlaceDisplay(place)
  const roleInStory = readRoleInStoryFromPlace(place)
  const occurrences = readMentionOccurrencesFromRow({ location: place, mention_occurrences: row?.mention_occurrences })
  const mentionText = primaryMentionText(occurrences) || (typeof place.original_text === 'string' ? place.original_text.trim() : '')
  const typeRaw = place.type
  const type = typeof typeRaw === 'string' ? typeRaw.trim() : ''
  return {
    label: display.name.trim(),
    type,
    formattedAddress: display.formattedAddress.trim(),
    roleInStory,
    mentionText,
    occurrences,
  }
}

export function placeEditFieldsEqual(a: PlaceEditFields, b: PlaceEditFields): boolean {
  return (
    a.label === b.label &&
    a.type === b.type &&
    a.formattedAddress === b.formattedAddress &&
    a.roleInStory === b.roleInStory &&
    a.mentionText === b.mentionText &&
    mentionOccurrencesEqual(a.occurrences, b.occurrences)
  )
}

function writePlaceLabel(place: Record<string, unknown>, label: string): void {
  const trimmed = label.trim()
  const loc = place.location
  if (loc && typeof loc === 'object' && !Array.isArray(loc)) {
    const o = cloneJson(loc) as Record<string, unknown>
    o.full = trimmed
    place.location = o
    return
  }
  if (typeof loc === 'string' || loc === undefined) {
    place.location = trimmed
    return
  }
  place.description = trimmed
}

function writeFormattedAddress(place: Record<string, unknown>, formattedAddress: string): void {
  const trimmed = formattedAddress.trim()
  const prevGeocode = place.geocode
  const geocode =
    prevGeocode && typeof prevGeocode === 'object' && !Array.isArray(prevGeocode)
      ? (cloneJson(prevGeocode) as Record<string, unknown>)
      : { geocode_type: 'manual', result: {} as Record<string, unknown> }
  const result =
    geocode.result && typeof geocode.result === 'object' && !Array.isArray(geocode.result)
      ? (cloneJson(geocode.result) as Record<string, unknown>)
      : ({} as Record<string, unknown>)
  if (trimmed) {
    result.formatted_address = trimmed
    result.processed_str = trimmed
  } else {
    delete result.formatted_address
    delete result.processed_str
  }
  geocode.result = result
  place.geocode = geocode
}

/** Apply editable fields to a copy of a place row (live preview). */
export function applyPlaceEditFields(
  place: Record<string, unknown>,
  fields: PlaceEditFields,
): Record<string, unknown> {
  const out = cloneJson(place) as Record<string, unknown>
  writePlaceLabel(out, fields.label)
  if (fields.type.trim()) {
    out.type = fields.type.trim()
  } else {
    delete out.type
  }
  writeFormattedAddress(out, fields.formattedAddress)
  out.role_in_story = fields.roleInStory.trim()
  const primary = primaryMentionText(fields.occurrences) || fields.mentionText.trim()
  out.original_text = primary
  out.mentions = fields.occurrences
    .filter((o) => !o.suppressed && o.mentionText.trim())
    .map((o) => ({ text: o.mentionText.trim() }))
  return out
}

/**
 * Shallow overlay patch for place fields only (no ``geocode`` / geometry).
 * Use when geometry is unchanged so complex shapes are not re-validated or re-sent.
 */
export function buildPlaceFieldsOnlyOverlayPatch(
  mergedPlace: Record<string, unknown>,
  fields: PlaceEditFields,
): Record<string, unknown> {
  const withFields = applyPlaceEditFields(mergedPlace, fields)
  const patch: Record<string, unknown> = {}

  const loc = mergedPlace.location
  if (loc && typeof loc === 'object' && !Array.isArray(loc)) {
    patch.location = withFields.location
  } else if (typeof loc === 'string' || loc === undefined) {
    patch.location = withFields.location
  } else {
    patch.description = withFields.description
  }

  if (withFields.type !== undefined) {
    patch.type = withFields.type
  }
  patch.role_in_story = withFields.role_in_story
  patch.original_text = withFields.original_text
  patch.occurrences = buildOccurrencesOverlayPayload(fields.occurrences)

  const baseline = readPlaceEditFields(mergedPlace)
  if (fields.formattedAddress.trim() !== baseline.formattedAddress) {
    return {
      ...patch,
      ...buildGeocodePatchForFormattedAddress(mergedPlace, fields.formattedAddress),
    }
  }
  return patch
}

/** Shallow overlay patch for ``locations.by_anchor`` (includes full ``geocode`` when geometry set). */
export function buildPlaceEditOverlayPatch(
  mergedPlace: Record<string, unknown>,
  fields: PlaceEditFields,
  geometry: Record<string, unknown> | null,
): Record<string, unknown> {
  const withFields = applyPlaceEditFields(mergedPlace, fields)
  const withGeometry = applyGeometryToPlaceRow(withFields, geometry)
  const patch: Record<string, unknown> = {}

  const loc = mergedPlace.location
  if (loc && typeof loc === 'object' && !Array.isArray(loc)) {
    patch.location = withGeometry.location
  } else if (typeof loc === 'string' || loc === undefined) {
    patch.location = withGeometry.location
  } else {
    patch.description = withGeometry.description
  }

  if (withGeometry.type !== undefined) {
    patch.type = withGeometry.type
  }
  patch.role_in_story = withGeometry.role_in_story
  patch.original_text = withGeometry.original_text
  patch.occurrences = buildOccurrencesOverlayPayload(fields.occurrences)

  if (geometry === null) {
    return { ...patch, ...buildGeocodePatchForClearGeometry(withFields) }
  }
  return applyOverlayPatchAfterGeometryAssignment({
    ...patch,
    ...buildGeocodePatchForGeometry(withFields, geometry),
  })
}
