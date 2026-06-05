import {
  deleteCanonicalOrganization,
  listCanonicalOrganizations,
  listCanonicalOrganizationTypes,
  type CanonicalOrganization,
  type CanonicalOrganizationListSort,
} from "@/lib/api"
import { placeExtractTypeLabel } from "@/lib/place-extract-type-label"
import type {
  CanonicalListBaseUrlState,
  CanonicalListPageConfig,
} from "@/lib/entityConfigs/canonicalListTypes"

export type OrganizationListUrlState = CanonicalListBaseUrlState<CanonicalOrganizationListSort>

export function parseOrganizationListArgs(sp: URLSearchParams): OrganizationListUrlState {
  const qRaw = sp.get("q") ?? ""
  const q = qRaw.trim()
  const typeRaw = sp.get("type") ?? ""
  const typeFilter = typeRaw && typeRaw !== "all" ? typeRaw : "all"
  const typeFilterParam = typeFilter === "all" ? undefined : typeFilter
  const sortRaw = sp.get("sort")
  const sortBy: CanonicalOrganizationListSort = sortRaw === "recent" ? "recent" : "label"
  const minMentions = Math.max(0, parseInt(sp.get("min_mentions") ?? "0", 10) || 0)
  const page = Math.max(1, parseInt(sp.get("page") ?? "1", 10) || 1)
  return {
    q,
    typeFilter,
    typeFilterParam,
    sortBy,
    minMentions,
    page,
  }
}

function organizationRowDescription(c: CanonicalOrganization): string {
  const parts: string[] = []
  if (c.organization_type) parts.push(placeExtractTypeLabel(c.organization_type))
  parts.push(c.status)
  parts.push(
    `${c.linked_substrate_count} linked organization${c.linked_substrate_count !== 1 ? "s" : ""}`,
  )
  if (c.mention_count !== undefined) {
    parts.push(`${c.mention_count} mention${c.mention_count !== 1 ? "s" : ""}`)
  }
  return parts.join(" • ")
}

export const organizationCanonicalListConfig: CanonicalListPageConfig<
  CanonicalOrganization,
  CanonicalOrganizationListSort,
  OrganizationListUrlState
> = {
  breadcrumbLabel: "Organizations",
  pageTitle: "Canonical organizations",
  routeSegment: "organizations",
  itemLabel: "organizations",
  emptyMessage: "No canonical organizations in this Stylebook yet",
  deleteTitle: "Delete canonical organization",
  deleteDescription: (label) =>
    `Delete "${label}"? Linked organizations return to the candidate queue. This cannot be undone.`,
  deleteErrorMessage: "Failed to delete canonical organization",
  parseListArgs: parseOrganizationListArgs,
  sortOptions: [
    { value: "label", label: "Name (A–Z)" },
    { value: "recent", label: "Recently active" },
  ],
  sortToUrlParam: (sort) => (sort === "label" ? undefined : "recent"),
  fetchTypes: listCanonicalOrganizationTypes,
  fetchCanonicals: async (stylebookSlug, projectFilterSlug, args, perPage) => {
    const offset = (args.page - 1) * perPage
    return listCanonicalOrganizations(
      stylebookSlug,
      args.q || undefined,
      perPage,
      offset,
      args.typeFilterParam,
      projectFilterSlug || undefined,
      {
        sort: args.sortBy,
        minMentions: args.minMentions,
      },
    )
  },
  deleteCanonical: async (id, stylebookSlug) => {
    await deleteCanonicalOrganization(id, stylebookSlug)
  },
  detailPath: (catalogBasePath, id) => `${catalogBasePath}/organizations/canonical/${id}`,
  renderRowDescription: organizationRowDescription,
}
