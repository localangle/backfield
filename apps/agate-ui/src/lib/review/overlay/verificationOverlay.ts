/**
 * Draft overlay state for processed-item verification (Issue 4).
 * Aligns with ``docs/API.md`` → processed item location overlay (v1).
 */

export function emptyOverlay(): Record<string, unknown> {
  return {
    locations: {
      by_anchor: {} as Record<string, unknown>,
      user_added: [] as unknown[],
      removed_anchors: [] as string[],
    },
  }
}

function cloneJson<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}

export function deepSortKeys(value: unknown): unknown {
  if (value === null || typeof value !== 'object') {
    return value
  }
  if (Array.isArray(value)) {
    return value.map(deepSortKeys)
  }
  const o = value as Record<string, unknown>
  const out: Record<string, unknown> = {}
  for (const k of Object.keys(o).sort()) {
    out[k] = deepSortKeys(o[k])
  }
  return out
}

export function overlaysStructurallyEqual(a: unknown, b: unknown): boolean {
  return JSON.stringify(deepSortKeys(a)) === JSON.stringify(deepSortKeys(b))
}

/**
 * Normalize overlay JSON so ``locations.by_anchor`` and ``locations.user_added`` exist.
 */
export function normalizeOverlay(
  overlay: Record<string, unknown> | null | undefined,
): Record<string, unknown> {
  const base = emptyOverlay()
  if (!overlay || typeof overlay !== 'object') {
    return cloneJson(base)
  }
  const out = cloneJson(overlay) as Record<string, unknown>
  // Recover mistaken double-wrap from early people-review PATCH calls ({ overlay: { people: … } }).
  const nested = out.overlay
  if (
    !out.people &&
    nested &&
    typeof nested === 'object' &&
    !Array.isArray(nested) &&
    (Object.prototype.hasOwnProperty.call(nested, 'people') ||
      Object.prototype.hasOwnProperty.call(nested, 'locations'))
  ) {
    return normalizeOverlay(nested as Record<string, unknown>)
  }
  const locRaw = out.locations
  if (!locRaw || typeof locRaw !== 'object' || Array.isArray(locRaw)) {
    out.locations = cloneJson(base.locations)
    return out
  }
  const loc = locRaw as Record<string, unknown>
  const by = loc.by_anchor
  loc.by_anchor =
    typeof by === 'object' && by !== null && !Array.isArray(by)
      ? { ...(by as Record<string, unknown>) }
      : {}
  const ua = loc.user_added
  loc.user_added = Array.isArray(ua) ? [...ua] : []
  const removed = loc.removed_anchors
  loc.removed_anchors = Array.isArray(removed)
    ? removed.filter((a): a is string => typeof a === 'string' && a.trim().length > 0)
    : []
  out.locations = loc
  const peopleRaw = out.people
  if (peopleRaw && typeof peopleRaw === 'object' && !Array.isArray(peopleRaw)) {
    const people = peopleRaw as Record<string, unknown>
    const byPeople = people.by_anchor
    people.by_anchor =
      typeof byPeople === 'object' && byPeople !== null && !Array.isArray(byPeople)
        ? { ...(byPeople as Record<string, unknown>) }
        : {}
    const uaPeople = people.user_added
    people.user_added = Array.isArray(uaPeople) ? [...uaPeople] : []
    const removedPeople = people.removed_anchors
    people.removed_anchors = Array.isArray(removedPeople)
      ? removedPeople.filter((a): a is string => typeof a === 'string' && a.trim().length > 0)
      : []
    out.people = people
  }
  const organizationsRaw = out.organizations
  if (organizationsRaw && typeof organizationsRaw === 'object' && !Array.isArray(organizationsRaw)) {
    const organizations = organizationsRaw as Record<string, unknown>
    const byOrganizations = organizations.by_anchor
    organizations.by_anchor =
      typeof byOrganizations === 'object' &&
      byOrganizations !== null &&
      !Array.isArray(byOrganizations)
        ? { ...(byOrganizations as Record<string, unknown>) }
        : {}
    const uaOrganizations = organizations.user_added
    organizations.user_added = Array.isArray(uaOrganizations) ? [...uaOrganizations] : []
    const removedOrganizations = organizations.removed_anchors
    organizations.removed_anchors = Array.isArray(removedOrganizations)
      ? removedOrganizations.filter(
          (a): a is string => typeof a === 'string' && a.trim().length > 0,
        )
      : []
    out.organizations = organizations
  }
  return out
}

function ensureLocations(draft: Record<string, unknown>): Record<string, unknown> {
  if (!draft.locations || typeof draft.locations !== 'object' || Array.isArray(draft.locations)) {
    draft.locations = cloneJson(emptyOverlay().locations) as Record<string, unknown>
  }
  const loc = draft.locations as Record<string, unknown>
  if (!loc.by_anchor || typeof loc.by_anchor !== 'object' || Array.isArray(loc.by_anchor)) {
    loc.by_anchor = {}
  }
  if (!Array.isArray(loc.user_added)) {
    loc.user_added = []
  }
  if (!Array.isArray(loc.removed_anchors)) {
    loc.removed_anchors = []
  }
  return loc
}

export type UserAddedPlaceOverlayInput = {
  anchor: string
  label: string
  locationType: string
  mentionText: string
  quoteText: string
  startChar: number
  endChar: number
  roleInStory?: string
  formattedAddress?: string | null
  geometry?: Record<string, unknown> | null
}

/** Build a ``locations.user_added`` row for reviewed-output materialization. */
export function buildUserAddedOverlayRow(input: UserAddedPlaceOverlayInput): Record<string, unknown> {
  const location: Record<string, unknown> = {
    description: input.label.trim(),
    original_text: input.mentionText.trim(),
    location: {
      full: input.label.trim(),
      type: input.locationType.trim(),
      components: {},
    },
    mentions: [{ text: input.mentionText.trim() }],
    mention_occurrences: [
      {
        mention_text: input.mentionText.trim(),
        quote_text: input.quoteText.trim(),
        start_char: input.startChar,
        end_char: input.endChar,
        occurrence_order: 0,
        suppressed: false,
        source_kind: 'manual_add',
      },
    ],
  }
  if (input.roleInStory?.trim()) {
    location.role_in_story = input.roleInStory.trim()
  }
  const formatted = input.formattedAddress?.trim()
  if (input.geometry && typeof input.geometry === 'object') {
    location.geocode = {
      geocode_type: 'manual',
      result: { geometry: cloneJson(input.geometry) },
    }
  } else if (formatted) {
    location.geocode = {
      geocode_type: 'manual',
      result: {
        formatted_address: formatted,
        processed_str: formatted,
      },
    }
  }
  return {
    id: input.anchor,
    location,
  }
}

/** Append or replace a user-added place row on the draft overlay (for reviewed JSON). */
export function appendUserAddedPlaceToOverlay(
  draft: Record<string, unknown>,
  row: Record<string, unknown>,
): Record<string, unknown> {
  const next = cloneJson(normalizeOverlay(draft)) as Record<string, unknown>
  const loc = ensureLocations(next)
  const anchor = typeof row.id === 'string' ? row.id : ''
  const ua = loc.user_added as unknown[]
  const rest = anchor
    ? ua.filter((entry) => {
        if (!entry || typeof entry !== 'object' || Array.isArray(entry)) return true
        return (entry as { id?: unknown }).id !== anchor
      })
    : ua
  loc.user_added = [...rest, row]
  return next
}

/** Overlay patch that removes a place from review (model row hidden; user row dropped). */
export function buildRemovePlaceOverlayPatch(
  draft: Record<string, unknown>,
  anchor: string,
  source: 'model' | 'user',
): Record<string, unknown> {
  const next = cloneJson(draft) as Record<string, unknown>
  const loc = ensureLocations(next)
  if (source === 'user') {
    const ua = loc.user_added as unknown[]
    loc.user_added = ua.filter((row) => {
      if (!row || typeof row !== 'object' || Array.isArray(row)) return true
      return (row as { id?: unknown }).id !== anchor
    })
  } else {
    const removed = loc.removed_anchors as string[]
    if (!removed.includes(anchor)) {
      removed.push(anchor)
    }
    const by = loc.by_anchor as Record<string, unknown>
    delete by[anchor]
  }
  return next
}

/**
 * True when the merged place row is treated as linked to a catalog canonical and must stay read-only here.
 */
export function isLocationLinkedToStylebookCanonical(location: unknown): boolean {
  if (!location || typeof location !== 'object' || Array.isArray(location)) {
    return false
  }
  const loc = location as Record<string, unknown>
  const sid = loc.stylebook_location_canonical_id
  if (typeof sid === 'string' && sid.trim().length > 0) {
    return true
  }
  if (typeof sid === 'number' && !Number.isNaN(sid)) {
    return true
  }
  if (loc.canonical_link_status === 'linked') {
    return true
  }
  const geocode = loc.geocode
  if (geocode && typeof geocode === 'object' && !Array.isArray(geocode)) {
    const res = (geocode as Record<string, unknown>).result
    if (res && typeof res === 'object' && !Array.isArray(res)) {
      const cid = (res as Record<string, unknown>).canonical_id
      if (typeof cid === 'string' && cid.trim().length > 0) {
        return true
      }
    }
  }
  return false
}

/**
 * Catalog canonical id for opening Stylebook from a linked place row (UUID string when present).
 */
export function getStylebookCanonicalHandoffId(location: unknown): string | null {
  if (!location || typeof location !== 'object' || Array.isArray(location)) {
    return null
  }
  const loc = location as Record<string, unknown>
  const sid = loc.stylebook_location_canonical_id
  if (typeof sid === 'string' && sid.trim().length > 0) {
    return sid.trim()
  }
  if (typeof sid === 'number' && !Number.isNaN(sid)) {
    return String(Math.trunc(sid))
  }
  const geocode = loc.geocode
  if (geocode && typeof geocode === 'object' && !Array.isArray(geocode)) {
    const res = (geocode as Record<string, unknown>).result
    if (res && typeof res === 'object' && !Array.isArray(res)) {
      const cid = (res as Record<string, unknown>).canonical_id
      if (typeof cid === 'string' && cid.trim().length > 0) {
        return cid.trim()
      }
    }
  }
  return null
}

export function getMergedRowAnchor(row: Record<string, unknown>): string {
  const a = row.anchor
  return typeof a === 'string' ? a : ''
}

export function getLocationDescription(location: unknown): string {
  if (!location || typeof location !== 'object' || Array.isArray(location)) {
    return ''
  }
  const d = (location as Record<string, unknown>).description
  return typeof d === 'string' ? d : ''
}

/**
 * Shallow-merge a ``description`` patch into ``locations.by_anchor[anchor]`` on the draft overlay.
 */
export function applyDescriptionPatch(
  draft: Record<string, unknown>,
  anchor: string,
  description: string,
): void {
  const loc = ensureLocations(draft)
  const by = loc.by_anchor as Record<string, unknown>
  const cur = by[anchor]
  const patch: Record<string, unknown> =
    typeof cur === 'object' && cur !== null && !Array.isArray(cur)
      ? { ...(cur as Record<string, unknown>) }
      : {}
  patch.description = description
  by[anchor] = patch
}

export function isApiConflictError(error: unknown): boolean {
  if (!(error instanceof Error)) {
    return false
  }
  return /\b409\b/.test(error.message)
}

function ensurePeople(draft: Record<string, unknown>): Record<string, unknown> {
  if (!draft.people || typeof draft.people !== 'object' || Array.isArray(draft.people)) {
    draft.people = {
      by_anchor: {},
      user_added: [],
      removed_anchors: [],
    }
  }
  const people = draft.people as Record<string, unknown>
  if (!people.by_anchor || typeof people.by_anchor !== 'object' || Array.isArray(people.by_anchor)) {
    people.by_anchor = {}
  }
  if (!Array.isArray(people.user_added)) {
    people.user_added = []
  }
  if (!Array.isArray(people.removed_anchors)) {
    people.removed_anchors = []
  }
  return people
}

/** Overlay patch that removes a person from review. */
export function buildRemovePersonOverlayPatch(
  draft: Record<string, unknown>,
  anchor: string,
  source: 'model' | 'user',
): Record<string, unknown> {
  const next = cloneJson(draft) as Record<string, unknown>
  const people = ensurePeople(next)
  if (source === 'user') {
    const ua = people.user_added as unknown[]
    people.user_added = ua.filter((row) => {
      if (!row || typeof row !== 'object' || Array.isArray(row)) return true
      return (row as { id?: unknown }).id !== anchor
    })
  } else {
    const removed = people.removed_anchors as string[]
    if (!removed.includes(anchor)) {
      removed.push(anchor)
    }
    const by = people.by_anchor as Record<string, unknown>
    delete by[anchor]
  }
  return next
}

/** Shallow-merge a person field patch into ``people.by_anchor[anchor]``. */
export function applyPersonAnchorPatch(
  draft: Record<string, unknown>,
  anchor: string,
  patch: Record<string, unknown>,
): Record<string, unknown> {
  const next = cloneJson(normalizeOverlay(draft)) as Record<string, unknown>
  const people = ensurePeople(next)
  const by = people.by_anchor as Record<string, unknown>
  const cur = by[anchor]
  by[anchor] =
    typeof cur === 'object' && cur !== null && !Array.isArray(cur)
      ? { ...(cur as Record<string, unknown>), ...patch }
      : { ...patch }
  return next
}

export type UserAddedPersonOverlayInput = {
  anchor: string
  name: string
  personType: string
  title?: string
  affiliation?: string
  nature?: string
  publicFigure?: boolean
  mentionText: string
  quoteText: string
  startChar: number
  endChar: number
  roleInStory?: string
}

/** Build a ``people.user_added`` row for reviewed-output materialization. */
export function buildUserAddedPersonOverlayRow(
  input: UserAddedPersonOverlayInput,
): Record<string, unknown> {
  const person: Record<string, unknown> = {
    name: input.name.trim(),
    type: input.personType.trim(),
    title: input.title?.trim() || '',
    affiliation: input.affiliation?.trim() || '',
    nature: input.nature?.trim() || 'other',
    public_figure: Boolean(input.publicFigure),
    mentions: [{ text: input.mentionText.trim() }],
    mention_occurrences: [
      {
        mention_text: input.mentionText.trim(),
        quote_text: input.quoteText.trim(),
        start_char: input.startChar,
        end_char: input.endChar,
        occurrence_order: 0,
        suppressed: false,
        source_kind: 'manual_add',
      },
    ],
  }
  if (input.roleInStory?.trim()) {
    person.role_in_story = input.roleInStory.trim()
  }
  return {
    id: input.anchor,
    person,
  }
}

/** Append or replace a user-added person row on the draft overlay. */
export function appendUserAddedPersonToOverlay(
  draft: Record<string, unknown>,
  row: Record<string, unknown>,
): Record<string, unknown> {
  const next = cloneJson(normalizeOverlay(draft)) as Record<string, unknown>
  const people = ensurePeople(next)
  const anchor = typeof row.id === 'string' ? row.id : ''
  const ua = people.user_added as unknown[]
  const rest = anchor
    ? ua.filter((entry) => {
        if (!entry || typeof entry !== 'object' || Array.isArray(entry)) return true
        return (entry as { id?: unknown }).id !== anchor
      })
    : ua
  people.user_added = [...rest, row]
  return next
}

function ensureOrganizations(draft: Record<string, unknown>): Record<string, unknown> {
  if (
    !draft.organizations ||
    typeof draft.organizations !== 'object' ||
    Array.isArray(draft.organizations)
  ) {
    draft.organizations = {
      by_anchor: {},
      user_added: [],
      removed_anchors: [],
    }
  }
  const organizations = draft.organizations as Record<string, unknown>
  if (
    !organizations.by_anchor ||
    typeof organizations.by_anchor !== 'object' ||
    Array.isArray(organizations.by_anchor)
  ) {
    organizations.by_anchor = {}
  }
  if (!Array.isArray(organizations.user_added)) {
    organizations.user_added = []
  }
  if (!Array.isArray(organizations.removed_anchors)) {
    organizations.removed_anchors = []
  }
  return organizations
}

export function buildRemoveOrganizationOverlayPatch(
  draft: Record<string, unknown>,
  anchor: string,
  source: 'model' | 'user',
): Record<string, unknown> {
  const next = cloneJson(draft) as Record<string, unknown>
  const organizations = ensureOrganizations(next)
  if (source === 'user') {
    const ua = organizations.user_added as unknown[]
    organizations.user_added = ua.filter((row) => {
      if (!row || typeof row !== 'object' || Array.isArray(row)) return true
      return (row as { id?: unknown }).id !== anchor
    })
  } else {
    const removed = organizations.removed_anchors as string[]
    if (!removed.includes(anchor)) {
      removed.push(anchor)
    }
    const by = organizations.by_anchor as Record<string, unknown>
    delete by[anchor]
  }
  return next
}

export function applyOrganizationAnchorPatch(
  draft: Record<string, unknown>,
  anchor: string,
  patch: Record<string, unknown>,
): Record<string, unknown> {
  const next = cloneJson(normalizeOverlay(draft)) as Record<string, unknown>
  const organizations = ensureOrganizations(next)
  const by = organizations.by_anchor as Record<string, unknown>
  const cur = by[anchor]
  by[anchor] =
    typeof cur === 'object' && cur !== null && !Array.isArray(cur)
      ? { ...(cur as Record<string, unknown>), ...patch }
      : { ...patch }
  return next
}

export type UserAddedOrganizationOverlayInput = {
  anchor: string
  name: string
  organizationType: string
  nature?: string
  mentionText: string
  quoteText: string
  startChar: number
  endChar: number
  roleInStory?: string
}

export function buildUserAddedOrganizationOverlayRow(
  input: UserAddedOrganizationOverlayInput,
): Record<string, unknown> {
  const organization: Record<string, unknown> = {
    name: input.name.trim(),
    type: input.organizationType.trim(),
    nature: input.nature?.trim() || 'other',
    mentions: [{ text: input.mentionText.trim() }],
    mention_occurrences: [
      {
        mention_text: input.mentionText.trim(),
        quote_text: input.quoteText.trim(),
        start_char: input.startChar,
        end_char: input.endChar,
        occurrence_order: 0,
        suppressed: false,
        source_kind: 'manual_add',
      },
    ],
  }
  if (input.roleInStory?.trim()) {
    organization.role_in_story = input.roleInStory.trim()
  }
  return {
    id: input.anchor,
    organization,
  }
}

export function appendUserAddedOrganizationToOverlay(
  draft: Record<string, unknown>,
  row: Record<string, unknown>,
): Record<string, unknown> {
  const next = cloneJson(normalizeOverlay(draft)) as Record<string, unknown>
  const organizations = ensureOrganizations(next)
  const anchor = typeof row.id === 'string' ? row.id : ''
  const ua = organizations.user_added as unknown[]
  const rest = anchor
    ? ua.filter((entry) => {
        if (!entry || typeof entry !== 'object' || Array.isArray(entry)) return true
        return (entry as { id?: unknown }).id !== anchor
      })
    : ua
  organizations.user_added = [...rest, row]
  return next
}
