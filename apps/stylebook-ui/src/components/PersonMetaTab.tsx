import React from "react"
import MetaTab, { type MetaTabConfig } from "@/components/MetaTab"
import {
  createStylebookCanonicalPersonMeta,
  deleteStylebookCanonicalPersonMeta,
  getStylebookCanonicalPersonMeta,
  updateStylebookCanonicalPersonMeta,
} from "@/lib/stylebook-api/meta"

const personMetaTabConfig: MetaTabConfig = {
  type: "person",
  displayName: { singular: "Person", plural: "People" },
  subtitle: "Additional details about this person.",
  api: {
    getMeta: (entityId, stylebookSlug) =>
      getStylebookCanonicalPersonMeta(stylebookSlug, String(entityId)),
    createMeta: (entityId, stylebookSlug, data) =>
      createStylebookCanonicalPersonMeta(stylebookSlug, String(entityId), data),
    updateMeta: (entityId, metaId, stylebookSlug, data) =>
      updateStylebookCanonicalPersonMeta(stylebookSlug, String(entityId), metaId, data),
    deleteMeta: (entityId, metaId, stylebookSlug) =>
      deleteStylebookCanonicalPersonMeta(stylebookSlug, String(entityId), metaId),
  },
}

interface PersonMetaTabProps {
  personId: string | null
  stylebookSlug: string
  onMetaUpdated?: () => void
}

export default function PersonMetaTab({
  personId,
  stylebookSlug,
  onMetaUpdated,
}: PersonMetaTabProps) {
  return (
    <MetaTab
      entityId={personId}
      projectSlug={stylebookSlug}
      config={personMetaTabConfig}
      onMetaUpdated={onMetaUpdated}
    />
  )
}
