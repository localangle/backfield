import {
  getCanonicalOrganization,
  getOrganization,
  getSuggestedOrganizationCanonicals,
  linkOrganizationSubstrateToCanonical,
  listCanonicalOrganizations,
  type CanonicalOrganization,
  type SuggestedOrganizationCanonicalItem,
} from "@/lib/api"
import type { LinkPickTableRow } from "@/components/LinkPickTable"
import { placeExtractTypeLabel } from "@/lib/place-extract-type-label"
import type { CanonicalLinkModalConfig } from "@/lib/entityConfigs/canonicalLinkModalTypes"

function canonicalToSuggestedRow(c: CanonicalOrganization): SuggestedOrganizationCanonicalItem {
  return {
    canonical_id: c.id,
    label: c.label,
    organization_type: c.organization_type ?? null,
  }
}

function organizationSuggestionDetailLine(s: SuggestedOrganizationCanonicalItem): string {
  const typeLabel = (s.organization_type ?? "").trim()
  return typeLabel ? placeExtractTypeLabel(typeLabel) : "—"
}

function suggestionToPickRow(s: SuggestedOrganizationCanonicalItem): LinkPickTableRow {
  return {
    rowKey: s.canonical_id,
    location: s.label,
    typeLabel:
      s.organization_type && String(s.organization_type).trim()
        ? placeExtractTypeLabel(s.organization_type)
        : "—",
    address: organizationSuggestionDetailLine(s),
  }
}

export const organizationCanonicalLinkModalConfig: CanonicalLinkModalConfig<
  SuggestedOrganizationCanonicalItem,
  CanonicalOrganization
> = {
  defaultTitle: "Link to canonical organization",
  searchInputId: "organization-canon-search",
  searchLabel: "Search Stylebook",
  searchPlaceholder: "Type to search names…",
  catalogNoun: "organizations",
  emptySearchMessage: "No organizations match your search.",
  linkActionLabel: "Link to this organization",
  table: {
    primaryColumnLabel: "Name",
    secondaryColumnLabel: "Type",
    includeAddress: true,
    includeType: true,
  },
  getLinkedCanonicalId: (substrate) => {
    const row = substrate as { stylebook_organization_canonical_id?: string | null }
    const cid = (row.stylebook_organization_canonical_id ?? "").trim()
    return cid ? cid : null
  },
  fetchSubstrate: (substrateId, projectSlug) => getOrganization(substrateId, projectSlug),
  fetchSuggestions: (projectSlug, substrateId) =>
    getSuggestedOrganizationCanonicals(projectSlug, substrateId),
  searchCanonicals: (stylebookSlug, q, projectSlug) =>
    listCanonicalOrganizations(stylebookSlug, q, 20, 0, undefined, projectSlug),
  fetchCanonical: (id, stylebookSlug, projectSlug) =>
    getCanonicalOrganization(id, stylebookSlug, projectSlug),
  linkSubstrate: async (substrateId, projectSlug, canonicalId) => {
    await linkOrganizationSubstrateToCanonical(substrateId, projectSlug, canonicalId)
  },
  canonicalToSuggestion: canonicalToSuggestedRow,
  suggestionToPickRow,
}
