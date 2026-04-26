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
  api: {
    getMeta: getCanonicalLocationMeta,
    createMeta: createCanonicalLocationMeta,
    updateMeta: updateCanonicalLocationMeta,
    deleteMeta: deleteCanonicalLocationMeta,
  },
}

interface LocationMetaTabProps {
  locationId: number | null
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
