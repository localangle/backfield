import EntitySelector from "@/components/EntitySelector"
import { workPickerConfig } from "@/lib/entityConfigs/connectionPickers"
import type { WorkPickerRow } from "@/lib/entityConfigs/connectionPickers"

interface WorkSelectorProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSelect: (workId: number, displayName?: string) => void
  projectSlug: string
  candidateNames?: string[]
  excludeIds?: number[]
}

export default function WorkSelector({
  open,
  onOpenChange,
  onSelect,
  projectSlug,
  candidateNames = [],
  excludeIds = [],
}: WorkSelectorProps) {
  return (
    <EntitySelector<WorkPickerRow>
      open={open}
      onOpenChange={onOpenChange}
      onSelect={onSelect}
      projectSlug={projectSlug}
      candidateNames={candidateNames}
      excludeIds={excludeIds}
      config={workPickerConfig}
    />
  )
}
