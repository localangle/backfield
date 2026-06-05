import {
  deleteCanonicalLocation,
  listCanonicalLocations,
  listCanonicalLocationTypes,
  type CanonicalListSort,
  type CanonicalLocation,
} from "@/lib/api"
import { placeExtractTypeLabel } from "@/lib/place-extract-type-label"
import type {
  CanonicalListBaseUrlState,
  CanonicalListPageConfig,
} from "@/lib/entityConfigs/canonicalListTypes"

export type LocationListUrlState = CanonicalListBaseUrlState<CanonicalListSort>

export function parseLocationListArgs(sp: URLSearchParams): LocationListUrlState {
  const qRaw = sp.get("q") ?? ""
  const q = qRaw.trim()
  const typeRaw = sp.get("type") ?? ""
  const typeFilter = typeRaw && typeRaw !== "all" ? typeRaw : "all"
  const typeFilterParam = typeFilter === "all" ? undefined : typeFilter
  const sortBy: CanonicalListSort = sp.get("sort") === "recent" ? "recent" : "label"
  const minMentions = Math.max(0, parseInt(sp.get("min_mentions") ?? "0", 10) || 0)
  const page = Math.max(1, parseInt(sp.get("page") ?? "1", 10) || 1)
  return { q, typeFilter, typeFilterParam, sortBy, minMentions, page }
}

function locationRowDescription(c: CanonicalLocation): string {
  const parts = [
    c.location_type ? placeExtractTypeLabel(c.location_type) : "—",
    c.status,
    `${c.linked_substrate_count} linked place${c.linked_substrate_count !== 1 ? "s" : ""}`,
  ]
  if (c.mention_count !== undefined) {
    parts.push(`${c.mention_count} mention${c.mention_count !== 1 ? "s" : ""}`)
  }
  return parts.join(" • ")
}

export const locationCanonicalListConfig: CanonicalListPageConfig<
  CanonicalLocation,
  CanonicalListSort,
  LocationListUrlState
> = {
  breadcrumbLabel: "Locations",
  pageTitle: "Canonical locations",
  routeSegment: "locations",
  itemLabel: "canonicals",
  emptyMessage: "No canonical locations in this Stylebook yet",
  deleteTitle: "Delete canonical location",
  deleteDescription: (label) =>
    `Delete "${label}"? Linked places return to the candidate queue. This cannot be undone.`,
  deleteErrorMessage: "Failed to delete canonical location",
  parseListArgs: parseLocationListArgs,
  sortOptions: [
    { value: "label", label: "Name (A–Z)" },
    { value: "recent", label: "Recently active" },
  ],
  sortToUrlParam: (sort) => (sort === "label" ? undefined : "recent"),
  fetchTypes: listCanonicalLocationTypes,
  fetchCanonicals: async (stylebookSlug, projectFilterSlug, args, perPage) => {
    const offset = (args.page - 1) * perPage
    return listCanonicalLocations(
      stylebookSlug,
      args.q || undefined,
      perPage,
      offset,
      args.typeFilterParam,
      projectFilterSlug || undefined,
      { sort: args.sortBy, minMentions: args.minMentions },
    )
  },
  deleteCanonical: async (id, stylebookSlug) => {
    await deleteCanonicalLocation(id, stylebookSlug)
  },
  detailPath: (catalogBasePath, id) => `${catalogBasePath}/locations/canonical/${id}`,
  renderRowDescription: locationRowDescription,
}
