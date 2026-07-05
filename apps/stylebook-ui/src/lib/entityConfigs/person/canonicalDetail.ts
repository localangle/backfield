import type { CanonicalDetailConfig } from "@/lib/entityConfigs/canonicalDetailTypes"
import type { LinkedPersonMention, LinkedPersonSubstrateItem } from "@/lib/api"
import { personNatureBadgeClass, personNatureDisplayLabel } from "@/lib/personMentionNature"
import { placeExtractTypeLabel } from "@/lib/place-extract-type-label"

function personSubstrateMetaLine(s: LinkedPersonSubstrateItem): string {
  const parts: string[] = []
  const typeLabel = (s.person_type || "").trim()
    ? placeExtractTypeLabel(s.person_type!)
    : "—"
  parts.push(typeLabel)
  if (s.title) parts.push(s.title)
  if (s.affiliation) parts.push(s.affiliation)
  return parts.join(" · ")
}

export const personCanonicalDetailConfig: CanonicalDetailConfig<
  LinkedPersonSubstrateItem,
  LinkedPersonMention
> = {
  entityType: "person",
  listBreadcrumbLabel: "People",
  deleteDialogTitle: "Delete person",
  deleteDialogDescription: (label) =>
    `Delete "${label}"? Linked people return to the candidate queue. This cannot be undone.`,
  sections: ["details", "mentions", "meta", "connections"],
  mentions: {
    description: "Article mentions are grouped by linked person. Unlink or reassign people below.",
    substrateDisplayMode: "selectable",
    substrateNoun: "person",
    columnHeaders: {
      substrateArticle: "Person / article",
      nature: "Nature",
      role: "Role in story",
      quotedText: "Quoted text",
    },
    getMentionSubstrateId: (m) => m.substrate_person_id,
    renderSubstrateSubtitle: personSubstrateMetaLine,
    getMentionNatureBadgeClass: (nature) => personNatureBadgeClass(nature ?? ""),
    getMentionNatureLabel: (nature) => personNatureDisplayLabel(nature ?? ""),
    emptySubstrateMentionsMessage: "No article mentions for this person.",
    noLinkedMentionsMessage: "No linked mentions.",
  },
}
