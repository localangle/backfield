import EntitySelector from "@/components/EntitySelector"
import { personPickerConfig } from "@/lib/entityConfigs/connectionPickers"
import type { PersonPickerRow } from "@/lib/entityConfigs/connectionPickers"

interface PersonSelectorProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSelect: (personId: number, displayName?: string) => void
  projectSlug: string
  candidateNames?: string[]
  excludeIds?: number[]
}

export default function PersonSelector({
  open,
  onOpenChange,
  onSelect,
  projectSlug,
  candidateNames = [],
  excludeIds = [],
}: PersonSelectorProps) {
  return (
    <EntitySelector<PersonPickerRow>
      open={open}
      onOpenChange={onOpenChange}
      onSelect={onSelect}
      projectSlug={projectSlug}
      candidateNames={candidateNames}
      excludeIds={excludeIds}
      config={personPickerConfig}
    />
  )
}
