import type { ReactNode } from "react"
import type { EntityType } from "@/lib/entityTypes"

export type CanonicalDetailSectionId =
  | "details"
  | "geography"
  | "mentions"
  | "meta"
  | "connections"

/** Minimal substrate shape for the shared mentions table. */
export interface CanonicalMentionSubstrate {
  id: number
  name: string
  project_slug: string
  project_name: string
}

/** Minimal mention row shape for the shared mentions table. */
export interface CanonicalMentionRow {
  mention_id: number
  article_id: number
  article_headline?: string | null
  article_url?: string | null
  original_text?: string | null
  mention_nature?: string | null
  description?: string | null
}

export interface CanonicalMentionsSectionConfig<
  TSubstrate extends CanonicalMentionSubstrate = CanonicalMentionSubstrate,
  TMention extends CanonicalMentionRow = CanonicalMentionRow,
> {
  description: string
  substrateDisplayMode?: "grouped" | "selectable"
  columnHeaders: {
    substrateArticle: string
    nature: string
    role: string
    quotedText: string
  }
  getMentionSubstrateId: (mention: TMention) => number
  /** Text shown under the substrate name (project badge is rendered by the shell). */
  renderSubstrateSubtitle: (substrate: TSubstrate) => ReactNode
  renderSubstrateHeaderExtra?: (substrate: TSubstrate) => ReactNode
  getMentionNatureBadgeClass: (nature: string | null | undefined) => string
  getMentionNatureLabel: (nature: string | null | undefined) => string
  emptySubstrateMentionsMessage: string
  noLinkedMentionsMessage: string
}

export interface CanonicalDetailConfig<
  TSubstrate extends CanonicalMentionSubstrate = CanonicalMentionSubstrate,
  TMention extends CanonicalMentionRow = CanonicalMentionRow,
> {
  entityType: EntityType
  listBreadcrumbLabel: string
  deleteDialogTitle: string
  deleteDialogDescription: (label: string) => string
  mentions: CanonicalMentionsSectionConfig<TSubstrate, TMention>
  /** Ordered section ids; geography is location-only. */
  sections: readonly CanonicalDetailSectionId[]
}
