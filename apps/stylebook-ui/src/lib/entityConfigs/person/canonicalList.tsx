import {
  deleteCanonicalPerson,
  listCanonicalPeople,
  listCanonicalPersonTypes,
  type CanonicalPerson,
  type CanonicalPersonListSort,
} from "@/lib/api"
import { placeExtractTypeLabel } from "@/lib/place-extract-type-label"
import type {
  CanonicalListBaseUrlState,
  CanonicalListFilterContext,
  CanonicalListPageConfig,
} from "@/lib/entityConfigs/canonicalListTypes"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

export type PersonListUrlState = CanonicalListBaseUrlState<CanonicalPersonListSort> & {
  publicFigureRaw: string
  titleFilter: string
  affiliationFilter: string
}

export function parsePersonListArgs(sp: URLSearchParams): PersonListUrlState {
  const qRaw = sp.get("q") ?? ""
  const q = qRaw.trim()
  const typeRaw = sp.get("type") ?? ""
  const typeFilter = typeRaw && typeRaw !== "all" ? typeRaw : "all"
  const typeFilterParam = typeFilter === "all" ? undefined : typeFilter
  const sortRaw = sp.get("sort")
  const sortBy: CanonicalPersonListSort =
    sortRaw === "recent" ? "recent" : "sort_key"
  const publicFigureRaw = sp.get("public_figure") ?? "all"
  const titleFilter = (sp.get("title") ?? "").trim()
  const affiliationFilter = (sp.get("affiliation") ?? "").trim()
  const minMentions = Math.max(0, parseInt(sp.get("min_mentions") ?? "0", 10) || 0)
  const page = Math.max(1, parseInt(sp.get("page") ?? "1", 10) || 1)
  return {
    q,
    typeFilter,
    typeFilterParam,
    sortBy,
    publicFigureRaw,
    titleFilter,
    affiliationFilter,
    minMentions,
    page,
  }
}

function personRowDescription(c: CanonicalPerson): string {
  const parts: string[] = []
  if (c.title) parts.push(c.title)
  if (c.affiliation) parts.push(c.affiliation)
  if (c.person_type) parts.push(placeExtractTypeLabel(c.person_type))
  if (c.public_figure) parts.push("Public figure")
  parts.push(c.status)
  parts.push(
    `${c.linked_substrate_count} linked person${c.linked_substrate_count !== 1 ? "s" : ""}`,
  )
  if (c.mention_count !== undefined) {
    parts.push(`${c.mention_count} mention${c.mention_count !== 1 ? "s" : ""}`)
  }
  return parts.join(" • ")
}

function renderPersonExtraFilters(ctx: CanonicalListFilterContext<CanonicalPersonListSort>) {
  const urlState = ctx.urlState as PersonListUrlState
  return (
    <>
      <div>
        <Label>Title</Label>
        <Input
          placeholder="Filter by title…"
          value={ctx.textQueries.title ?? ""}
          onChange={(e) => ctx.setTextQuery("title", e.target.value)}
        />
      </div>
      <div>
        <Label>Affiliation</Label>
        <Input
          placeholder="Filter by affiliation…"
          value={ctx.textQueries.affiliation ?? ""}
          onChange={(e) => ctx.setTextQuery("affiliation", e.target.value)}
        />
      </div>
      <div>
        <Label>Public figure</Label>
        <Select
          value={urlState.publicFigureRaw}
          onValueChange={(v) => ctx.setSelectParam("public_figure", v)}
        >
          <SelectTrigger>
            <SelectValue placeholder="All" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All</SelectItem>
            <SelectItem value="yes">Yes</SelectItem>
            <SelectItem value="no">No</SelectItem>
          </SelectContent>
        </Select>
      </div>
    </>
  )
}

export const personCanonicalListConfig: CanonicalListPageConfig<
  CanonicalPerson,
  CanonicalPersonListSort,
  PersonListUrlState
> = {
  breadcrumbLabel: "People",
  pageTitle: "Canonical people",
  routeSegment: "people",
  itemLabel: "people",
  emptyMessage: "No canonical people in this Stylebook yet",
  deleteTitle: "Delete canonical person",
  deleteDescription: (label) =>
    `Delete "${label}"? Linked people return to the candidate queue. This cannot be undone.`,
  deleteErrorMessage: "Failed to delete canonical person",
  parseListArgs: parsePersonListArgs,
  extraDebouncedParamKeys: ["title", "affiliation"],
  sortOptions: [
    { value: "sort_key", label: "Last name (A–Z)" },
    { value: "recent", label: "Recently active" },
  ],
  sortToUrlParam: (sort) => (sort === "sort_key" ? undefined : "recent"),
  fetchTypes: listCanonicalPersonTypes,
  fetchCanonicals: async (stylebookSlug, projectFilterSlug, args, perPage) => {
    const publicFigureFilter =
      args.publicFigureRaw === "yes" ? true : args.publicFigureRaw === "no" ? false : undefined
    const offset = (args.page - 1) * perPage
    return listCanonicalPeople(
      stylebookSlug,
      args.q || undefined,
      perPage,
      offset,
      args.typeFilterParam,
      projectFilterSlug || undefined,
      {
        sort: args.sortBy,
        publicFigure: publicFigureFilter,
        minMentions: args.minMentions,
        title: args.titleFilter || undefined,
        affiliation: args.affiliationFilter || undefined,
      },
    )
  },
  deleteCanonical: async (id, stylebookSlug) => {
    await deleteCanonicalPerson(id, stylebookSlug)
  },
  detailPath: (catalogBasePath, id) => `${catalogBasePath}/people/canonical/${id}`,
  renderRowDescription: personRowDescription,
  renderExtraFilters: renderPersonExtraFilters,
}
