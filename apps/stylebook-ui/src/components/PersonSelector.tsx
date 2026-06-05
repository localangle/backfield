import { useMemo } from "react"
import EntitySelector from "@/components/EntitySelector"
import { createPersonPickerConfig } from "@/lib/entityConfigs/connectionPickers"
import type { PersonPickerRow } from "@/lib/entityConfigs/connectionPickers"

interface PersonSelectorProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSelect: (personId: string | number, displayName?: string) => void
  projectSlug: string
  stylebookSlug: string
  candidateNames?: string[]
  excludeIds?: Array<string | number>
}

export default function PersonSelector({
  open,
  onOpenChange,
  onSelect,
  projectSlug,
  stylebookSlug,
  candidateNames = [],
  excludeIds = [],
}: PersonSelectorProps) {
  const config = useMemo(() => createPersonPickerConfig(stylebookSlug), [stylebookSlug])

  return (
    <EntitySelector<PersonPickerRow>
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
