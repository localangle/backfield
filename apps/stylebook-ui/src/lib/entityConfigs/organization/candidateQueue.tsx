import type { OrganizationCandidate } from "@/lib/api"
import {
  acceptOrganizationCandidate,
  deferOrganizationCandidate,
  getCanonicalOrganization,
  getOrganizationCandidateContext,
  getSuggestedOrganizationCanonicals,
  linkOrganizationSubstrateToCanonical,
  listOrganizationCandidates,
  updateOrganizationCandidateNote,
} from "@/lib/api"
import { placeExtractTypeLabel } from "@/lib/place-extract-type-label"
import { OrganizationCanonicalLinkModal } from "@/components/OrganizationCanonicalLinkModal"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import type { CandidateQueueLinkModalProps, CandidateQueuePageConfig } from "@/lib/entityConfigs/candidateQueueTypes"
import { truncateCellText } from "@/lib/candidateQueueTableLayout"

function OrganizationLinkModal({
  substrateId,
  initialSearchQuery,
  ...props
}: CandidateQueueLinkModalProps) {
  return (
    <OrganizationCanonicalLinkModal
      open={props.open}
      onOpenChange={props.onOpenChange}
      projectSlug={props.projectSlug}
      stylebookSlug={props.stylebookSlug}
      substrateOrganizationId={substrateId}
      initialCanonicalId={props.initialCanonicalId}
      initialSearchQuery={initialSearchQuery}
      title={props.title}
      onLinked={props.onLinked}
      onDone={props.onDone}
    />
  )
}

export const organizationCandidateQueueConfig: CandidateQueuePageConfig<OrganizationCandidate> = {
  entitySlug: "organizations",

  copy: {
    pageTitle: "Organization candidates",
    breadcrumbEntityLabel: "Organizations",
    canonicalButtonLabel: "Canonical organizations",
    reviewQueueDescription:
      "Unlinked organizations for this project. Use Link to attach to an existing organization, or Create new to add one.",
    searchInputId: "organization-candidate-search",
    searchPlaceholder: "Search name…",
    emptyState: "No unlinked organizations.",
    primaryColumnHeader: "Name",
    createdToastTitle: "Organization created",
    linkedToastTitle: "Linked to organization",
    followupCheckingMessage: "Checking the open queue for related organizations…",
    linkModalTitle: "Link candidate to organization",
    candidateFallbackLabel: (id) => `Organization ${id}`,
    suggestionLabels: {
      link: "Link to existing organization",
      create_new: "Create new organization",
      defer: "Defer (remove from linking queue)",
    },
    actionLabels: {
      link: {
        default: "Link to existing organization",
        suggested: "Link to existing organization",
        suggestedWithId: "Link to suggested organization",
        titleDefault: "Link to existing organization",
        titleSuggested: "Suggested: link to existing organization",
        titleSuggestedWithId: "Suggested: link now",
      },
      create: {
        default: "Create new organization",
        creating: "Creating organization",
        suggested: "Suggested: create new organization",
        titleDefault: "Create new organization",
        titleSuggested: "Suggested: create new organization",
      },
      defer: {
        default: "Defer — remove from linking queue",
        suggested: "Suggested: defer (remove from linking queue)",
        titleDefault: "Defer — remove from linking queue",
        titleSuggested: "Suggested: defer (remove from linking queue)",
      },
    },
    potentialLinks: {
      candidateNounPlural: "organizations",
      linkActionLabel: "Link this candidate to the new organization",
      primaryColumnLabel: "Name",
      includeType: true,
      includeAddress: false,
    },
  },

  api: {
    list: async (projectSlug, status, options) => {
      const res = await listOrganizationCandidates(projectSlug, status, options)
      return {
        candidates: res.candidates,
        total: res.total,
        has_next: res.has_next,
        has_prev: res.has_prev,
      }
    },
    getContext: getOrganizationCandidateContext,
    defer: async (projectSlug, candidateId) => {
      await deferOrganizationCandidate(projectSlug, candidateId)
    },
    updateNote: async (projectSlug, candidateId, note) => {
      await updateOrganizationCandidateNote(projectSlug, candidateId, note)
    },
    linkToCanonical: async (candidateId, projectSlug, canonicalId) => {
      await linkOrganizationSubstrateToCanonical(candidateId, projectSlug, canonicalId)
    },
    getSuggestedCanonicalId: (c) => {
      const cid = (c.canonical_suggestion?.stylebook_organization_canonical_id ?? "").trim()
      return cid || null
    },
    getSuggestedCanonicals: async (projectSlug, candidateId, limit) => {
      const res = await getSuggestedOrganizationCanonicals(projectSlug, candidateId, limit)
      return {
        suggestions: res.suggestions.map((s) => ({
          canonical_id: s.canonical_id,
          label: s.label,
        })),
      }
    },
    getCanonicalLabel: async (canonicalId, stylebookSlug, projectSlug) => {
      const canon = await getCanonicalOrganization(canonicalId, stylebookSlug, projectSlug)
      return (canon.label ?? "").trim() || canonicalId
    },
    acceptCreateNew: async (projectSlug, candidateId, body) => {
      const acceptRes = await acceptOrganizationCandidate(
        projectSlug,
        candidateId,
        body as Parameters<typeof acceptOrganizationCandidate>[2],
      )
      const cid = acceptRes.stylebook_organization_canonical_id
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
  ],

  tableLayout: {
    colgroup: [{ width: "52%" }, { width: "18%" }, { width: "11rem" }],
  },

  mapFollowupRow: (c) => ({
    rowKey: c.id,
    location: c.suggested_name || "—",
    typeLabel: c.suggested_type ? placeExtractTypeLabel(c.suggested_type) : "—",
    address: "—",
  }),

  linkModal: OrganizationLinkModal,

  onOpenLinkModal: (c) => ({
    initialCanonicalId: null,
    initialSearchQuery: (c.suggested_name ?? "").trim() || null,
  }),

  createDialog: {
    title: "Create new organization",
    description: (stylebookLabel) => (
      <>
        Add a canonical organization to{" "}
        <span className="font-semibold text-foreground">{stylebookLabel}</span>
      </>
    ),
    entityNoun: "organization",
    submitLabel: "Create organization",
    creatingLabel: "Creating…",
    initDraft: (c) => ({
      label: (c.suggested_name ?? "").trim(),
    }),
    renderFields: ({ draft, setDraft, candidate, accepting }) => (
      <>
        <div className="space-y-2">
          <Label htmlFor="create-organization-name">Name</Label>
          <Input
            id="create-organization-name"
            value={String(draft.label ?? "")}
            onChange={(e) => setDraft({ label: e.target.value })}
            autoFocus
            disabled={accepting}
          />
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
      if (!label) return "Enter a name for the new organization."
      return null
    },
    buildAcceptBody: (draft, candidate) => ({
      create_new: true,
      name: String(draft.label ?? "").trim(),
      organization_type: candidate.suggested_type ?? null,
    }),
    getDraftLabelForNudge: (draft) => String(draft.label ?? ""),
    acceptMissingIdError:
      "Organization was created, but the server did not return its id. Reload the page to open the new catalog entry.",
  },
}
