import React from "react"
import MetaTab, { type MetaTabConfig } from "@/components/MetaTab"
import {
  createCanonicalLocationMeta,
  deleteCanonicalLocationMeta,
  getCanonicalLocationMeta,
  updateCanonicalLocationMeta,
} from "@/lib/stylebook-api/meta"

const locationMetaTabConfig: MetaTabConfig = {
  type: "location",
  displayName: { singular: "Location", plural: "Locations" },
  subtitle: "Additional details about this location.",
  api: {
    getMeta: (entityId, projectSlug) => getCanonicalLocationMeta(String(entityId), projectSlug),
    createMeta: (entityId, projectSlug, data) =>
      createCanonicalLocationMeta(String(entityId), projectSlug, data),
    updateMeta: (entityId, metaId, projectSlug, data) =>
      updateCanonicalLocationMeta(String(entityId), metaId, projectSlug, data),
    deleteMeta: (entityId, metaId, projectSlug) =>
      deleteCanonicalLocationMeta(String(entityId), metaId, projectSlug),
  },
}

interface LocationMetaTabProps {
  locationId: string | null
  projectSlug: string
  onMetaUpdated?: () => void
}

export default function LocationMetaTab({ locationId, projectSlug, onMetaUpdated }: LocationMetaTabProps) {
  return (
    <MetaTab
      entityId={locationId}
      projectSlug={projectSlug}
      config={locationMetaTabConfig}
      onMetaUpdated={onMetaUpdated}
    />
  )
}
