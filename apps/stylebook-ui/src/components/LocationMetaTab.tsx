import React from "react"
import MetaTab, { type MetaTabConfig } from "@/components/MetaTab"
import {
  createStylebookCanonicalLocationMeta,
  deleteStylebookCanonicalLocationMeta,
  getStylebookCanonicalLocationMeta,
  updateStylebookCanonicalLocationMeta,
} from "@/lib/stylebook-api/meta"

const locationMetaTabConfig: MetaTabConfig = {
  type: "location",
  displayName: { singular: "Location", plural: "Locations" },
  subtitle: "Additional details about this location.",
  api: {
    getMeta: (entityId, stylebookSlug) =>
      getStylebookCanonicalLocationMeta(stylebookSlug, String(entityId)),
    createMeta: (entityId, stylebookSlug, data) =>
      createStylebookCanonicalLocationMeta(stylebookSlug, String(entityId), data),
    updateMeta: (entityId, metaId, stylebookSlug, data) =>
      updateStylebookCanonicalLocationMeta(stylebookSlug, String(entityId), metaId, data),
    deleteMeta: (entityId, metaId, stylebookSlug) =>
      deleteStylebookCanonicalLocationMeta(stylebookSlug, String(entityId), metaId),
  },
}

interface LocationMetaTabProps {
  locationId: string | null
  stylebookSlug: string
  onMetaUpdated?: () => void
}

export default function LocationMetaTab({
  locationId,
  stylebookSlug,
  onMetaUpdated,
}: LocationMetaTabProps) {
  return (
    <MetaTab
      entityId={locationId}
      projectSlug={stylebookSlug}
      config={locationMetaTabConfig}
      onMetaUpdated={onMetaUpdated}
    />
  )
}
