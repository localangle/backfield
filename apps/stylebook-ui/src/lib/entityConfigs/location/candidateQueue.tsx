import type { Candidate } from "@/lib/api"
import {
  acceptCandidate,
  clearLocationCandidateRecommendation,
  deferCandidate,
  getCandidateContext,
  getCanonicalLocation,
  getSuggestedCanonicals,
  linkSubstrateToCanonical,
  listCandidates,
  listLocationCandidateTypes,
  updateCandidateNote,
} from "@/lib/api"
import {
  PLACE_EXTRACT_LOCATION_TYPES,
  placeExtractTypeLabel,
  sortReviewQueueTypeFilterOptions,
} from "@/lib/place-extract-type-label"
import { truncateCellText } from "@/lib/candidateQueueTableLayout"
import { CanonicalLinkModal } from "@/components/CanonicalLinkModal"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import type { CandidateQueueLinkModalProps, CandidateQueuePageConfig } from "@/lib/entityConfigs/candidateQueueTypes"

function LocationLinkModal({
  substrateId,
  initialSearchQuery,
  ...props
}: CandidateQueueLinkModalProps) {
  return (
    <CanonicalLinkModal
      open={props.open}
      onOpenChange={props.onOpenChange}
      projectSlug={props.projectSlug}
      stylebookSlug={props.stylebookSlug}
      substrateLocationId={substrateId}
      initialCanonicalId={props.initialCanonicalId}
      initialSearchQuery={initialSearchQuery}
      title={props.title}
      onLinked={props.onLinked}
      onDone={props.onDone}
    />
  )
}

function defaultNewCanonicalLabel(c: Candidate): string {
  const fromName = (c.suggested_name ?? "").trim()
  if (fromName) return fromName
  return (c.suggested_formatted_address ?? "").trim()
}

function defaultNewCanonicalLocationType(c: Candidate): string {
  const t = (c.suggested_type ?? "").trim().toLowerCase()
  if (t && (PLACE_EXTRACT_LOCATION_TYPES as readonly string[]).includes(t)) return t
  return "place"
}

const createModalTypeOptions = sortReviewQueueTypeFilterOptions([...PLACE_EXTRACT_LOCATION_TYPES])

export const locationCandidateQueueConfig: CandidateQueuePageConfig<Candidate> = {
  entitySlug: "locations",
  aiReviewEntityType: "location",

  copy: {
    pageTitle: "Location candidates",
    breadcrumbEntityLabel: "Locations",
    canonicalButtonLabel: "Canonical locations",
    reviewQueueDescription:
      "Unlinked locations for this project. Use “Link” to attach to an existing canonical, or “Create new” to add a new one.",
    searchInputId: "candidate-search",
    searchPlaceholder: "Search name…",
    emptyState: "No unlinked locations.",
    primaryColumnHeader: "Location",
    createdToastTitle: "Canonical created",
    linkedToastTitle: "Linked to canonical",
    followupCheckingMessage: "Checking the open queue for related locations…",
    linkModalTitle: "Link candidate to canonical",
    candidateFallbackLabel: (id) => `Location ${id}`,
    suggestionLabels: {
      link: "Link to existing canonical",
      create_new: "Create new canonical",
      defer: "Defer (remove from linking queue)",
    },
    actionLabels: {
      link: {
        default: "Link to existing canonical",
        suggested: "Link to existing canonical",
        suggestedWithId: "Link to suggested canonical",
        titleDefault: "Link to existing canonical",
        titleSuggested: "Suggested: link to existing canonical",
        titleSuggestedWithId: "Suggested: link now",
      },
      create: {
        default: "Create new canonical",
        creating: "Creating canonical",
        suggested: "Suggested: create new canonical from this place",
        titleDefault: "Create new canonical from this place",
        titleSuggested: "Suggested: create new canonical from this place",
      },
      defer: {
        default: "Defer — remove from linking queue",
        suggested: "Suggested: defer (remove from linking queue)",
        titleDefault: "Defer — remove from linking queue",
        titleSuggested: "Suggested: defer (remove from linking queue)",
      },
    },
    potentialLinks: {
      candidateNounPlural: "locations",
      linkActionLabel: "Link this candidate to the new canonical",
      primaryColumnLabel: "Location",
    },
  },

  api: {
    list: async (projectSlug, status, options) => {
      const res = await listCandidates(projectSlug, status, false, options)
      return {
        candidates: res.candidates,
        total: res.total,
        has_next: res.has_next,
        has_prev: res.has_prev,
      }
    },
    listTypes: listLocationCandidateTypes,
    getContext: getCandidateContext,
    defer: async (projectSlug, candidateId) => {
      await deferCandidate(projectSlug, candidateId)
    },
    clearRecommendation: async (projectSlug, candidateId) => {
      await clearLocationCandidateRecommendation(projectSlug, candidateId)
    },
    updateNote: async (projectSlug, candidateId, note) => {
      await updateCandidateNote(projectSlug, candidateId, note)
    },
    linkToCanonical: async (candidateId, projectSlug, canonicalId) => {
      await linkSubstrateToCanonical(candidateId, projectSlug, canonicalId)
    },
    getSuggestedCanonicalId: (c) => {
      const cid = (c.canonical_suggestion?.stylebook_location_canonical_id ?? "").trim()
      return cid || null
    },
    getSuggestedCanonicals: async (projectSlug, candidateId, limit) => {
      const res = await getSuggestedCanonicals(projectSlug, candidateId, limit)
      return {
        suggestions: res.suggestions.map((s) => ({
          canonical_id: s.canonical_id,
          label: s.label,
        })),
      }
    },
    getCanonicalLabel: async (canonicalId, stylebookSlug, projectSlug) => {
      const canon = await getCanonicalLocation(canonicalId, stylebookSlug, projectSlug)
      return (canon.label ?? "").trim() || canonicalId
    },
    acceptCreateNew: async (projectSlug, candidateId, body) => {
      const acceptRes = await acceptCandidate(
        projectSlug,
        candidateId,
        body as Parameters<typeof acceptCandidate>[2],
      )
      const cid = acceptRes.stylebook_location_canonical_id
      return { canonicalId: typeof cid === "string" ? cid : "" }
    },
  },

  columns: [
    {
      id: "type",
      header: "Type",
      className: "min-w-0 overflow-hidden align-top",
      render: (c) => {
        const typeLabel = c.suggested_type ? placeExtractTypeLabel(c.suggested_type) : "—"
        return truncateCellText(typeLabel, typeLabel !== "—" ? typeLabel : undefined)
      },
    },
    {
      id: "address",
      header: "Address",
      render: (c) =>
        truncateCellText(
          c.suggested_formatted_address || "—",
          c.suggested_formatted_address || undefined,
        ),
    },
    {
      id: "created",
      header: "Created",
      className: "text-muted-foreground text-sm whitespace-nowrap",
      render: (c) => (c.created_at ? new Date(c.created_at).toLocaleDateString() : "—"),
    },
  ],

  tableLayout: {
    colgroup: [
      { width: "27%" },
      { width: "12%" },
      { width: "27%" },
      { width: "10%" },
      { width: "13rem" },
    ],
    actionsColumnWidth: "13rem",
  },

  typeFilter: {
    labelTypeOptions: (typeList) =>
      sortReviewQueueTypeFilterOptions(typeList).map((t) => ({
        value: t,
        label: placeExtractTypeLabel(t),
      })),
  },

  mapFollowupRow: (c) => ({
    rowKey: c.id,
    location: c.suggested_name || "—",
    typeLabel: c.suggested_type ? placeExtractTypeLabel(c.suggested_type) : "—",
    address: c.suggested_formatted_address || "—",
  }),

  linkModal: LocationLinkModal,

  onOpenLinkModal: (c) => ({
    initialCanonicalId: null,
    initialSearchQuery: (c.suggested_name ?? "").trim() || null,
  }),

  createDialog: {
    title: "Create new canonical",
    description: (stylebookLabel) => (
      <>
        Create new canonical object in{" "}
        <span className="font-semibold text-foreground">{stylebookLabel}</span>
      </>
    ),
    entityNoun: "canonical",
    submitLabel: "Create canonical",
    creatingLabel: "Creating…",
    initDraft: (c) => ({
      label: defaultNewCanonicalLabel(c),
      locationType: defaultNewCanonicalLocationType(c),
    }),
    renderFields: ({ draft, setDraft, candidate, accepting }) => (
      <>
        <div className="space-y-2">
          <Label htmlFor="create-canonical-type">Location type</Label>
          <Select
            value={String(draft.locationType ?? "")}
            onValueChange={(v) => setDraft({ locationType: v })}
            disabled={accepting}
          >
            <SelectTrigger id="create-canonical-type">
              <SelectValue placeholder="Select type" />
            </SelectTrigger>
            <SelectContent>
              {createModalTypeOptions.map((t) => (
                <SelectItem key={t} value={t}>
                  {placeExtractTypeLabel(t)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-2">
          <Label htmlFor="create-canonical-name">Canonical label</Label>
          <Input
            id="create-canonical-name"
            value={String(draft.label ?? "")}
            onChange={(e) => setDraft({ label: e.target.value })}
            placeholder="e.g. Dolton, IL"
            autoFocus
            disabled={accepting}
          />
        </div>
        {candidate?.suggested_formatted_address ? (
          <p className="text-xs text-muted-foreground">
            Geocoded address: {candidate.suggested_formatted_address}
          </p>
        ) : null}
      </>
    ),
    validate: (draft) => {
      const name = String(draft.label ?? "").trim()
      if (!name) return "Enter a label for the new canonical."
      const location_type = String(draft.locationType ?? "").trim().toLowerCase()
      if (
        !location_type ||
        !(PLACE_EXTRACT_LOCATION_TYPES as readonly string[]).includes(location_type)
      ) {
        return "Select a valid location type."
      }
      return null
    },
    buildAcceptBody: (draft) => ({
      create_new: true,
      name: String(draft.label ?? "").trim(),
      location_type: String(draft.locationType ?? "").trim().toLowerCase(),
    }),
    getDraftLabelForNudge: (draft) => String(draft.label ?? ""),
    acceptMissingIdError:
      "Canonical was created, but the server did not return its id. Reload the page if you need to link similar candidates from the toast.",
  },
}
