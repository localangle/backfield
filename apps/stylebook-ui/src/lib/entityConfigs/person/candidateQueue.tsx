import type { PersonCandidate } from "@/lib/api"
import {
  acceptPersonCandidate,
  clearPersonCandidateRecommendation,
  deferPersonCandidate,
  getCanonicalPerson,
  getPersonCandidateContext,
  getSuggestedPersonCanonicals,
  linkPersonSubstrateToCanonical,
  listPersonCandidates,
  updatePersonCandidateNote,
} from "@/lib/api"
import { placeExtractTypeLabel } from "@/lib/place-extract-type-label"
import { PersonCanonicalLinkModal } from "@/components/PersonCanonicalLinkModal"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import type { CandidateQueueLinkModalProps, CandidateQueuePageConfig } from "@/lib/entityConfigs/candidateQueueTypes"
import { truncateCellText } from "@/lib/candidateQueueTableLayout"

function PersonLinkModal({
  substrateId,
  initialSearchQuery,
  ...props
}: CandidateQueueLinkModalProps) {
  return (
    <PersonCanonicalLinkModal
      open={props.open}
      onOpenChange={props.onOpenChange}
      projectSlug={props.projectSlug}
      stylebookSlug={props.stylebookSlug}
      substratePersonId={substrateId}
      initialCanonicalId={props.initialCanonicalId}
      initialSearchQuery={initialSearchQuery}
      title={props.title}
      onLinked={props.onLinked}
      onDone={props.onDone}
    />
  )
}

function personCandidateDetailLine(c: PersonCandidate): string {
  const parts = [(c.suggested_title ?? "").trim(), (c.suggested_affiliation ?? "").trim()].filter(
    Boolean,
  )
  return parts.length > 0 ? parts.join(" · ") : "—"
}

export const personCandidateQueueConfig: CandidateQueuePageConfig<PersonCandidate> = {
  entitySlug: "people",
  aiReviewEntityType: "person",

  copy: {
    pageTitle: "People candidates",
    breadcrumbEntityLabel: "People",
    canonicalButtonLabel: "Canonical people",
    reviewQueueDescription:
      "Unlinked people for this project. Use Link to attach to an existing person, or Create new to add one.",
    searchInputId: "person-candidate-search",
    searchPlaceholder: "Search name…",
    emptyState: "No unlinked people.",
    primaryColumnHeader: "Name",
    createdToastTitle: "Person created",
    linkedToastTitle: "Linked to person",
    followupCheckingMessage: "Checking the open queue for related people…",
    linkModalTitle: "Link candidate to person",
    candidateFallbackLabel: (id) => `Person ${id}`,
    suggestionLabels: {
      link: "Link to existing person",
      create_new: "Create new person",
      defer: "Defer (remove from linking queue)",
    },
    actionLabels: {
      link: {
        default: "Link to existing person",
        suggested: "Link to existing person",
        suggestedWithId: "Link to suggested person",
        titleDefault: "Link to existing person",
        titleSuggested: "Suggested: link to existing person",
        titleSuggestedWithId: "Suggested: link now",
      },
      create: {
        default: "Create new person",
        creating: "Creating person",
        suggested: "Suggested: create new person",
        titleDefault: "Create new person",
        titleSuggested: "Suggested: create new person",
      },
      defer: {
        default: "Defer — remove from linking queue",
        suggested: "Suggested: defer (remove from linking queue)",
        titleDefault: "Defer — remove from linking queue",
        titleSuggested: "Suggested: defer (remove from linking queue)",
      },
    },
    potentialLinks: {
      candidateNounPlural: "people",
      linkActionLabel: "Link this candidate to the new person",
      primaryColumnLabel: "Name",
      secondaryColumnLabel: "Affiliation",
      includeType: false,
    },
  },

  api: {
    list: async (projectSlug, status, options) => {
      const res = await listPersonCandidates(projectSlug, status, options)
      return {
        candidates: res.candidates,
        total: res.total,
        has_next: res.has_next,
        has_prev: res.has_prev,
      }
    },
    getContext: getPersonCandidateContext,
    defer: async (projectSlug, candidateId) => {
      await deferPersonCandidate(projectSlug, candidateId)
    },
    clearRecommendation: async (projectSlug, candidateId) => {
      await clearPersonCandidateRecommendation(projectSlug, candidateId)
    },
    updateNote: async (projectSlug, candidateId, note) => {
      await updatePersonCandidateNote(projectSlug, candidateId, note)
    },
    linkToCanonical: async (candidateId, projectSlug, canonicalId) => {
      await linkPersonSubstrateToCanonical(candidateId, projectSlug, canonicalId)
    },
    getSuggestedCanonicalId: (c) => {
      const cid = (c.canonical_suggestion?.stylebook_person_canonical_id ?? "").trim()
      return cid || null
    },
    getSuggestedCanonicals: async (projectSlug, candidateId, limit) => {
      const res = await getSuggestedPersonCanonicals(projectSlug, candidateId, limit)
      return {
        suggestions: res.suggestions.map((s) => ({
          canonical_id: s.canonical_id,
          label: s.label,
        })),
      }
    },
    getCanonicalLabel: async (canonicalId, stylebookSlug, projectSlug) => {
      const canon = await getCanonicalPerson(canonicalId, stylebookSlug, projectSlug)
      return (canon.label ?? "").trim() || canonicalId
    },
    acceptCreateNew: async (projectSlug, candidateId, body) => {
      const acceptRes = await acceptPersonCandidate(
        projectSlug,
        candidateId,
        body as Parameters<typeof acceptPersonCandidate>[2],
      )
      const cid = acceptRes.stylebook_person_canonical_id
      return { canonicalId: typeof cid === "string" ? cid.trim() : "" }
    },
  },

  columns: [
    {
      id: "type",
      header: "Type",
      render: (c) => {
        const label = c.suggested_type ? placeExtractTypeLabel(c.suggested_type) : "—"
        return truncateCellText(label, label !== "—" ? label : undefined)
      },
    },
    {
      id: "title",
      header: "Title",
      render: (c) => truncateCellText(c.suggested_title || "—", c.suggested_title || undefined),
    },
    {
      id: "affiliation",
      header: "Affiliation",
      render: (c) =>
        truncateCellText(c.suggested_affiliation || "—", c.suggested_affiliation || undefined),
    },
  ],

  tableLayout: {
    colgroup: [
      { width: "34%" },
      { width: "12%" },
      { width: "14%" },
      { width: "15%" },
      { width: "11rem" },
    ],
  },

  mapFollowupRow: (c) => ({
    rowKey: c.id,
    location: c.suggested_name || "—",
    typeLabel: c.suggested_type ? placeExtractTypeLabel(c.suggested_type) : "—",
    address: personCandidateDetailLine(c),
  }),

  linkModal: PersonLinkModal,

  onOpenLinkModal: (c) => ({
    initialCanonicalId: null,
    initialSearchQuery: (c.suggested_name ?? "").trim() || null,
  }),

  createDialog: {
    title: "Create new person",
    description: (stylebookLabel) => (
      <>
        Add a canonical person to{" "}
        <span className="font-semibold text-foreground">{stylebookLabel}</span>
      </>
    ),
    entityNoun: "person",
    submitLabel: "Create person",
    creatingLabel: "Creating…",
    initDraft: (c) => ({
      label: (c.suggested_name ?? "").trim(),
      title: (c.suggested_title ?? "").trim(),
      affiliation: (c.suggested_affiliation ?? "").trim(),
      publicFigure: Boolean(c.suggested_public_figure),
    }),
    renderFields: ({ draft, setDraft, candidate, accepting }) => (
      <>
        <div className="space-y-2">
          <Label htmlFor="create-person-name">Name</Label>
          <Input
            id="create-person-name"
            value={String(draft.label ?? "")}
            onChange={(e) => setDraft({ label: e.target.value })}
            autoFocus
            disabled={accepting}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="create-person-title">Title</Label>
          <Input
            id="create-person-title"
            value={String(draft.title ?? "")}
            onChange={(e) => setDraft({ title: e.target.value })}
            disabled={accepting}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="create-person-affiliation">Affiliation</Label>
          <Input
            id="create-person-affiliation"
            value={String(draft.affiliation ?? "")}
            onChange={(e) => setDraft({ affiliation: e.target.value })}
            disabled={accepting}
          />
        </div>
        <div className="flex items-center gap-2">
          <Checkbox
            id="create-person-public"
            checked={draft.publicFigure === true}
            onCheckedChange={(v) => setDraft({ publicFigure: v === true })}
            disabled={accepting}
          />
          <Label htmlFor="create-person-public">Public figure</Label>
        </div>
        {candidate?.suggested_type ? (
          <p className="text-xs text-muted-foreground">
            Type: {placeExtractTypeLabel(candidate.suggested_type)}
          </p>
        ) : null}
      </>
    ),
    validate: (draft) => {
      const label = String(draft.label ?? "").trim()
      if (!label) return "Enter a name for the new person."
      return null
    },
    buildAcceptBody: (draft, candidate) => ({
      create_new: true,
      name: String(draft.label ?? "").trim(),
      title: String(draft.title ?? "").trim() || null,
      affiliation: String(draft.affiliation ?? "").trim() || null,
      public_figure: draft.publicFigure === true,
      person_type: candidate.suggested_type ?? null,
    }),
    getDraftLabelForNudge: (draft) => String(draft.label ?? ""),
    acceptMissingIdError:
      "Person was created, but the server did not return its id. Reload the page to open the new catalog entry.",
  },
}
