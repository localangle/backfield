import type { CanonicalDetailConfig } from "@/lib/entityConfigs/canonicalDetailTypes"
import {
  mentionNatureBadgeClass,
  mentionNatureDisplayLabel,
} from "@/lib/mentionArticleDisplay"
import { placeExtractTypeLabel } from "@/lib/place-extract-type-label"
import type { LinkedMention, LinkedSubstrateItem } from "@/lib/api"

export const locationCanonicalDetailConfig: CanonicalDetailConfig<
  LinkedSubstrateItem,
  LinkedMention
> = {
  entityType: "location",
  listBreadcrumbLabel: "Locations",
  deleteDialogTitle: "Delete canonical location",
  deleteDialogDescription: (label) =>
    `Delete "${label}"? Linked places return to the candidate queue. This cannot be undone.`,
  sections: ["details", "geography", "mentions", "meta", "connections"],
  mentions: {
    description: "Article mentions are grouped by place. Unlink or reassign places below.",
    substrateDisplayMode: "selectable",
    substrateNoun: "place",
    columnHeaders: {
      substrateArticle: "Place / article",
      nature: "Nature",
      role: "Type / role",
      quotedText: "Quoted text",
    },
    getMentionSubstrateId: (m) => m.substrate_location_id,
    renderSubstrateSubtitle: (s) => {
      const typeLabel = (s.location_type || "").trim()
        ? placeExtractTypeLabel(s.location_type)
        : "—"
      const address = (s.formatted_address ?? "").trim() || "—"
      return `${typeLabel} · ${address}`
    },
    getMentionNatureBadgeClass: mentionNatureBadgeClass,
    getMentionNatureLabel: mentionNatureDisplayLabel,
    emptySubstrateMentionsMessage: "No article mentions for this place.",
    noLinkedMentionsMessage: "No linked mentions.",
  },
}
