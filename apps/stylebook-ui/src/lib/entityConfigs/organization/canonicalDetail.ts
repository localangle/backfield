import type { CanonicalDetailConfig } from "@/lib/entityConfigs/canonicalDetailTypes"
import type { LinkedOrganizationMention, LinkedOrganizationSubstrateItem } from "@/lib/api"
import {
  organizationNatureBadgeClass,
  organizationNatureDisplayLabel,
} from "@/lib/organizationMentionNature"
import { placeExtractTypeLabel } from "@/lib/place-extract-type-label"

function organizationSubstrateMetaLine(s: LinkedOrganizationSubstrateItem): string {
  const typeLabel = (s.organization_type || "").trim()
    ? placeExtractTypeLabel(s.organization_type!)
    : "—"
  return typeLabel
}

export const organizationCanonicalDetailConfig: CanonicalDetailConfig<
  LinkedOrganizationSubstrateItem,
  LinkedOrganizationMention
> = {
  entityType: "organization",
  listBreadcrumbLabel: "Organizations",
  deleteDialogTitle: "Delete organization",
  deleteDialogDescription: (label) =>
    `Delete "${label}"? Linked organizations return to the candidate queue. This cannot be undone.`,
  sections: ["details", "mentions", "meta", "connections"],
  mentions: {
    description:
      "Article mentions are grouped by linked organization. Unlink or reassign organizations below.",
    columnHeaders: {
      substrateArticle: "Organization / article",
      nature: "Nature",
      role: "Role in story",
      quotedText: "Quoted text",
    },
    getMentionSubstrateId: (m) => m.substrate_organization_id,
    renderSubstrateSubtitle: organizationSubstrateMetaLine,
    getMentionNatureBadgeClass: (nature) => organizationNatureBadgeClass(nature ?? ""),
    getMentionNatureLabel: (nature) => organizationNatureDisplayLabel(nature ?? ""),
    emptySubstrateMentionsMessage: "No article mentions for this organization.",
    noLinkedMentionsMessage: "No linked mentions.",
  },
}
