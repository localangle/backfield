import type { LinkPickTableRow } from "@/components/LinkPickTable"

export type CanonicalLinkModalTableConfig = {
  primaryColumnLabel?: string
  secondaryColumnLabel?: string
  includeAddress?: boolean
  includeType?: boolean
}

export type CanonicalLinkModalConfig<
  TSuggestion extends { canonical_id: string; label: string },
  TCanonical extends { id: string; label: string },
> = {
  defaultTitle: string
  searchInputId: string
  searchLabel: string
  searchPlaceholder: string
  catalogNoun: string
  emptySearchMessage: string
  linkActionLabel: string
  table: CanonicalLinkModalTableConfig
  getLinkedCanonicalId: (substrate: unknown) => string | null
  fetchSubstrate: (substrateId: number, projectSlug: string) => Promise<unknown>
  fetchSuggestions: (
    projectSlug: string,
    substrateId: number,
  ) => Promise<{ suggestions: TSuggestion[] }>
  searchCanonicals: (
    stylebookSlug: string,
    q: string,
    projectSlug: string,
  ) => Promise<{ canonicals: TCanonical[] }>
  fetchCanonical: (
    id: string,
    stylebookSlug: string,
    projectSlug: string,
  ) => Promise<TCanonical>
  linkSubstrate: (
    substrateId: number,
    projectSlug: string,
    canonicalId: string,
  ) => Promise<void>
  canonicalToSuggestion: (c: TCanonical) => TSuggestion
  suggestionToPickRow: (s: TSuggestion) => LinkPickTableRow
}

export type CanonicalLinkModalGenericProps<
  TSuggestion extends { canonical_id: string; label: string },
  TCanonical extends { id: string; label: string },
> = {
  open: boolean
  onOpenChange: (open: boolean) => void
  projectSlug: string
  stylebookSlug: string
  substrateId: number | null
  onDone: () => void
  onLinked?: (canonical: { id: string; label: string }) => void
  title?: string
  initialCanonicalId?: string | null
  initialSearchQuery?: string | null
  excludeCanonicalId?: string | null
  config: CanonicalLinkModalConfig<TSuggestion, TCanonical>
}
