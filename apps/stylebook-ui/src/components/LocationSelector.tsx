import { useMemo } from "react"
import EntitySelector from "@/components/EntitySelector"
import { createLocationPickerConfig } from "@/lib/entityConfigs/connectionPickers"
import type { LocationPickerRow } from "@/lib/entityConfigs/connectionPickers"

interface LocationSelectorProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSelect: (locationId: string | number, displayName?: string) => void
  projectSlug: string
  stylebookSlug: string
  candidateNames?: string[]
  excludeIds?: Array<string | number>
}

export default function LocationSelector({
  open,
  onOpenChange,
  onSelect,
  projectSlug,
  stylebookSlug,
  candidateNames = [],
  excludeIds = [],
}: LocationSelectorProps) {
  const config = useMemo(() => createLocationPickerConfig(stylebookSlug), [stylebookSlug])

  return (
    <EntitySelector<LocationPickerRow>
      open={open}
      onOpenChange={onOpenChange}
      onSelect={onSelect}
      projectSlug={projectSlug}
      candidateNames={candidateNames}
      excludeIds={excludeIds}
      config={config}
    />
  )
}
