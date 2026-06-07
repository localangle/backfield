import type { ComponentType, ReactNode } from "react"
import type { LinkPickTableRow } from "@/components/LinkPickTable"

/** Base candidate shape both entity types satisfy for queue behavior. */
export type QueueCandidateBase = {
  id: number
  suggested_name?: string
  suggested_type?: string | null
  created_at?: string | null
  note?: string | null
  canonical_review_lines?: string[] | null
  defer_display_message?: string | null
  canonical_suggestion?: {
    suggested_action?: string | null
  } | null
}

export type CandidateQueueStatus = "open" | "deferred"

export type PaginatedListResult<T> = {
  candidates: T[]
  total: number
  has_next: boolean
  has_prev: boolean
}

export type CandidateContextResult = {
  note?: string | null
  examples: Array<{ article_id: number; article_headline?: string | null; text: string }>
}

export type CandidateQueueApiAdapter<TCandidate extends QueueCandidateBase> = {
  list: (
    projectSlug: string,
    status: CandidateQueueStatus,
    options: { limit: number; offset: number; q?: string; type_filter?: string },
  ) => Promise<PaginatedListResult<TCandidate>>

  listTypes?: (projectSlug: string, status: CandidateQueueStatus) => Promise<{ types: string[] }>

  getContext: (projectSlug: string, candidateId: number, limit: number) => Promise<CandidateContextResult>

  defer: (projectSlug: string, candidateId: number) => Promise<void>
  updateNote: (projectSlug: string, candidateId: number, note: string | null) => Promise<void>
  linkToCanonical: (candidateId: number, projectSlug: string, canonicalId: string) => Promise<void>

  getSuggestedCanonicalId: (candidate: TCandidate) => string | null
  getSuggestedCanonicals: (
    projectSlug: string,
    candidateId: number,
    limit: number,
  ) => Promise<{ suggestions: Array<{ canonical_id: string; label: string }> }>
  getCanonicalLabel: (canonicalId: string, stylebookSlug: string, projectSlug: string) => Promise<string>

  acceptCreateNew: (
    projectSlug: string,
    candidateId: number,
    body: unknown,
  ) => Promise<{ canonicalId: string }>
}

export type CandidateQueueColumn<TCandidate> = {
  id: string
  header: string
  className?: string
  render: (candidate: TCandidate) => ReactNode
}

export type CandidateQueueTableLayout = {
  colgroup?: Array<{ width: string }>
  actionsColumnWidth?: string
}

export type CandidateQueueSuggestionLabels = {
  link: string
  create_new: string
  defer: string
}

export type CandidateQueueActionLabels = {
  link: {
    default: string
    suggested: string
    suggestedWithId: string
    titleDefault: string
    titleSuggested: string
    titleSuggestedWithId: string
  }
  create: {
    default: string
    creating: string
    suggested: string
    titleDefault: string
    titleSuggested: string
  }
  defer: {
    default: string
    suggested: string
    titleDefault: string
    titleSuggested: string
  }
}

export type CandidateQueueLinkModalProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  projectSlug: string
  stylebookSlug: string
  substrateId: number | null
  initialCanonicalId: string | null
  initialSearchQuery?: string | null
  title: string
  onLinked: (payload: { id: string; label: string }) => void
  onDone: () => void
}

export type CandidateQueueCreateDialogConfig<TCandidate extends QueueCandidateBase> = {
  title: string
  description: (stylebookLabel: string) => ReactNode
  entityNoun: string
  submitLabel: string
  creatingLabel: string
  initDraft: (candidate: TCandidate) => Record<string, unknown>
  renderFields: (args: {
    draft: Record<string, unknown>
    setDraft: (patch: Record<string, unknown>) => void
    candidate: TCandidate | undefined
    accepting: boolean
  }) => ReactNode
  validate: (draft: Record<string, unknown>) => string | null
  buildAcceptBody: (draft: Record<string, unknown>, candidate: TCandidate) => unknown
  getDraftLabelForNudge: (draft: Record<string, unknown>) => string
  acceptMissingIdError: string
}

export type CandidateQueuePageConfig<TCandidate extends QueueCandidateBase> = {
  entitySlug: "locations" | "people" | "organizations"

  copy: {
    pageTitle: string
    breadcrumbEntityLabel: string
    canonicalButtonLabel: string
    reviewQueueDescription: string
    searchInputId: string
    searchPlaceholder: string
    emptyState: string
    primaryColumnHeader: string
    createdToastTitle: string
    linkedToastTitle: string
    followupCheckingMessage: string
    linkModalTitle: string
    candidateFallbackLabel: (id: number) => string
    suggestionLabels: CandidateQueueSuggestionLabels
    actionLabels: CandidateQueueActionLabels
    potentialLinks: {
      candidateNounPlural: string
      linkActionLabel: string
      primaryColumnLabel: string
      secondaryColumnLabel?: string
      includeType?: boolean
      includeAddress?: boolean
    }
  }

  api: CandidateQueueApiAdapter<TCandidate>

  columns: CandidateQueueColumn<TCandidate>[]

  tableLayout?: CandidateQueueTableLayout

  /** Optional type filter (location: enabled; person: omit). */
  typeFilter?: {
    labelTypeOptions: (types: string[]) => Array<{ value: string; label: string }>
  }

  mapFollowupRow: (candidate: TCandidate) => LinkPickTableRow

  linkModal: ComponentType<CandidateQueueLinkModalProps>

  createDialog: CandidateQueueCreateDialogConfig<TCandidate>

  onOpenLinkModal?: (candidate: TCandidate) => {
    initialCanonicalId: string | null
    initialSearchQuery?: string | null
  }
}
