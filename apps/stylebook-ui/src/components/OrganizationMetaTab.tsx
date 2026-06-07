import React from "react"
import MetaTab, { type MetaTabConfig } from "@/components/MetaTab"
import {
  createStylebookCanonicalOrganizationMeta,
  deleteStylebookCanonicalOrganizationMeta,
  getStylebookCanonicalOrganizationMeta,
  updateStylebookCanonicalOrganizationMeta,
} from "@/lib/stylebook-api/meta"

const organizationMetaTabConfig: MetaTabConfig = {
  type: "organization",
  displayName: { singular: "Organization", plural: "Organizations" },
  subtitle: "Additional details about this organization.",
  api: {
    getMeta: (entityId, stylebookSlug) =>
      getStylebookCanonicalOrganizationMeta(stylebookSlug, String(entityId)),
    createMeta: (entityId, stylebookSlug, data) =>
      createStylebookCanonicalOrganizationMeta(stylebookSlug, String(entityId), data),
    updateMeta: (entityId, metaId, stylebookSlug, data) =>
      updateStylebookCanonicalOrganizationMeta(stylebookSlug, String(entityId), metaId, data),
    deleteMeta: (entityId, metaId, stylebookSlug) =>
      deleteStylebookCanonicalOrganizationMeta(stylebookSlug, String(entityId), metaId),
  },
}

interface OrganizationMetaTabProps {
  organizationId: string | null
  stylebookSlug: string
  onMetaUpdated?: () => void
}

export default function OrganizationMetaTab({
  organizationId,
  stylebookSlug,
  onMetaUpdated,
}: OrganizationMetaTabProps) {
  return (
    <MetaTab
      entityId={organizationId}
      projectSlug={stylebookSlug}
      config={organizationMetaTabConfig}
      onMetaUpdated={onMetaUpdated}
    />
  )
}
