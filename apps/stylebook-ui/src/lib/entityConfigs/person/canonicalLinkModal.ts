import {
  getCanonicalPerson,
  getPerson,
  getSuggestedPersonCanonicals,
  linkPersonSubstrateToCanonical,
  listCanonicalPeople,
  type CanonicalPerson,
  type SuggestedPersonCanonicalItem,
} from "@/lib/api"
import type { LinkPickTableRow } from "@/components/LinkPickTable"
import { placeExtractTypeLabel } from "@/lib/place-extract-type-label"
import type { CanonicalLinkModalConfig } from "@/lib/entityConfigs/canonicalLinkModalTypes"

function canonicalToSuggestedRow(c: CanonicalPerson): SuggestedPersonCanonicalItem {
  return {
    canonical_id: c.id,
    label: c.label,
    person_type: c.person_type ?? null,
    title: c.title ?? null,
    affiliation: c.affiliation ?? null,
  }
}

function personSuggestionDetailLine(s: SuggestedPersonCanonicalItem): string {
  const parts = [(s.title ?? "").trim(), (s.affiliation ?? "").trim()].filter(Boolean)
  return parts.length > 0 ? parts.join(" · ") : "—"
}

function suggestionToPickRow(s: SuggestedPersonCanonicalItem): LinkPickTableRow {
  return {
    rowKey: s.canonical_id,
    location: s.label,
    typeLabel:
      s.person_type && String(s.person_type).trim()
        ? placeExtractTypeLabel(s.person_type)
        : "—",
    address: personSuggestionDetailLine(s),
  }
}

export const personCanonicalLinkModalConfig: CanonicalLinkModalConfig<
  SuggestedPersonCanonicalItem,
  CanonicalPerson
> = {
  defaultTitle: "Link to canonical person",
  searchInputId: "person-canon-search",
  searchLabel: "Search Stylebook",
  searchPlaceholder: "Type to search names…",
  catalogNoun: "people",
  emptySearchMessage: "No people match your search.",
  linkActionLabel: "Link to this person",
  table: {
    primaryColumnLabel: "Name",
    secondaryColumnLabel: "Affiliation",
    includeAddress: true,
    includeType: false,
  },
  getLinkedCanonicalId: (substrate) => {
    const row = substrate as { stylebook_person_canonical_id?: string | null }
    const cid = (row.stylebook_person_canonical_id ?? "").trim()
    return cid ? cid : null
  },
  fetchSubstrate: (substrateId, projectSlug) => getPerson(substrateId, projectSlug),
  fetchSuggestions: (projectSlug, substrateId) =>
    getSuggestedPersonCanonicals(projectSlug, substrateId),
  searchCanonicals: (stylebookSlug, q, projectSlug) =>
    listCanonicalPeople(stylebookSlug, q, 20, 0, undefined, projectSlug),
  fetchCanonical: (id, stylebookSlug, projectSlug) =>
    getCanonicalPerson(id, stylebookSlug, projectSlug),
  linkSubstrate: async (substrateId, projectSlug, canonicalId) => {
    await linkPersonSubstrateToCanonical(substrateId, projectSlug, canonicalId)
  },
  canonicalToSuggestion: canonicalToSuggestedRow,
  suggestionToPickRow,
}
