import { useMemo } from "react"
import EntitySelector from "@/components/EntitySelector"
import { createOrganizationPickerConfig } from "@/lib/entityConfigs/connectionPickers"
import type { OrganizationPickerRow } from "@/lib/entityConfigs/connectionPickers"

interface OrganizationSelectorProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSelect: (organizationId: string | number, displayName?: string) => void
  projectSlug: string
  stylebookSlug: string
  candidateNames?: string[]
  excludeIds?: Array<string | number>
}

export default function OrganizationSelector({
  open,
  onOpenChange,
  onSelect,
  projectSlug,
  stylebookSlug,
  candidateNames = [],
  excludeIds = [],
}: OrganizationSelectorProps) {
  const config = useMemo(() => createOrganizationPickerConfig(stylebookSlug), [stylebookSlug])

  return (
    <EntitySelector<OrganizationPickerRow>
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
