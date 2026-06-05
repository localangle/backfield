import {
  getCanonicalLocation,
  getLocation,
  getSuggestedCanonicals,
  linkSubstrateToCanonical,
  listCanonicalLocations,
  type CanonicalLocation,
  type SuggestedCanonicalItem,
} from "@/lib/api"
import type { LinkPickTableRow } from "@/components/LinkPickTable"
import { placeExtractTypeLabel } from "@/lib/place-extract-type-label"
import type { CanonicalLinkModalConfig } from "@/lib/entityConfigs/canonicalLinkModalTypes"

function canonicalToSuggestedRow(c: CanonicalLocation): SuggestedCanonicalItem {
  return {
    canonical_id: c.id,
    label: c.label,
    location_type: c.location_type ?? null,
    formatted_address: c.formatted_address ?? null,
  }
}

function suggestionToPickRow(s: SuggestedCanonicalItem): LinkPickTableRow {
  return {
    rowKey: s.canonical_id,
    location: s.label,
    typeLabel:
      s.location_type && String(s.location_type).trim()
        ? placeExtractTypeLabel(s.location_type)
        : "—",
    address: (s.formatted_address ?? "").trim() || "—",
  }
}

export const locationCanonicalLinkModalConfig: CanonicalLinkModalConfig<
  SuggestedCanonicalItem,
  CanonicalLocation
> = {
  defaultTitle: "Link to canonical",
  searchInputId: "canon-search",
  searchLabel: "Search catalog",
  searchPlaceholder: "Type to search canonical labels…",
  catalogNoun: "canonicals",
  emptySearchMessage: "No canonicals match your search.",
  linkActionLabel: "Link to this canonical",
  table: {
    includeAddress: false,
  },
  getLinkedCanonicalId: (substrate) => {
    const loc = substrate as { stylebook_location_canonical_id?: string | null }
    const cid = (loc.stylebook_location_canonical_id ?? "").trim()
    return cid ? cid : null
  },
  fetchSubstrate: (substrateId, projectSlug) => getLocation(substrateId, projectSlug),
  fetchSuggestions: (projectSlug, substrateId) =>
    getSuggestedCanonicals(projectSlug, substrateId),
  searchCanonicals: (stylebookSlug, q, projectSlug) =>
    listCanonicalLocations(stylebookSlug, q, 20, 0, undefined, projectSlug),
  fetchCanonical: (id, stylebookSlug, projectSlug) =>
    getCanonicalLocation(id, stylebookSlug, projectSlug),
  linkSubstrate: async (substrateId, projectSlug, canonicalId) => {
    await linkSubstrateToCanonical(substrateId, projectSlug, canonicalId)
  },
  canonicalToSuggestion: canonicalToSuggestedRow,
  suggestionToPickRow,
}
