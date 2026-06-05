import type { ReactNode } from "react"
import type { Project } from "@/lib/api"

export type CanonicalListBaseUrlState<TSort extends string> = {
  q: string
  typeFilter: string
  typeFilterParam: string | undefined
  sortBy: TSort
  minMentions: number
  page: number
}

export type CanonicalListQueryResult<TCanonical> = {
  canonicals: TCanonical[]
  total: number
  has_next: boolean
  has_prev: boolean
}

export type CanonicalListFilterContext<TSort extends string> = {
  urlState: CanonicalListBaseUrlState<TSort> & Record<string, unknown>
  textQueries: Record<string, string>
  setTextQuery: (key: string, value: string) => void
  setSelectParam: (key: string, value: string, omitWhen?: string) => void
  setTypeFilterParam: (value: string) => void
  setProjectFilterParam: (value: string) => void
  setSortParam: (value: TSort) => void
  setMinMentionsParam: (n: number) => void
  projects: Project[]
  projectsLoading: boolean
  orderedTypeOptions: string[]
  projectFilterSlug: string | undefined
}

export type CanonicalListPageConfig<
  TCanonical,
  TSort extends string,
  TUrlState extends CanonicalListBaseUrlState<TSort> = CanonicalListBaseUrlState<TSort>,
> = {
  breadcrumbLabel: string
  pageTitle: string
  routeSegment: string
  itemLabel: string
  perPage?: number
  emptyMessage: string
  deleteTitle: string
  deleteDescription: (label: string) => ReactNode
  deleteErrorMessage: string
  parseListArgs: (sp: URLSearchParams) => TUrlState
  extraDebouncedParamKeys?: string[]
  sortOptions: { value: TSort; label: string }[]
  sortToUrlParam: (sort: TSort) => string | undefined
  fetchTypes: (stylebookSlug: string) => Promise<{ types: string[] }>
  fetchCanonicals: (
    stylebookSlug: string,
    projectFilterSlug: string | undefined,
    args: TUrlState,
    perPage: number,
  ) => Promise<CanonicalListQueryResult<TCanonical>>
  deleteCanonical: (id: string, stylebookSlug: string) => Promise<void>
  detailPath: (catalogBasePath: string, id: string) => string
  renderRowDescription: (canonical: TCanonical) => ReactNode
  renderExtraFilters?: (ctx: CanonicalListFilterContext<TSort>) => ReactNode
}
