import { CanonicalLinkModalGeneric } from "@/components/CanonicalLinkModalGeneric"
import { locationCanonicalLinkModalConfig } from "@/lib/entityConfigs/location/canonicalLinkModal"

export function CanonicalLinkModal(props: {
  open: boolean
  onOpenChange: (open: boolean) => void
  projectSlug: string
  stylebookSlug: string
  /** Substrate location id (open candidate or linked row for relink/move). */
  substrateLocationId: number | null
  onDone: () => void
  onLinked?: (canonical: { id: string; label: string }) => void
  title?: string
  /** When set, surface this canonical first (e.g. pre-filled from row suggestion). */
  initialCanonicalId?: string | null
  /** Pre-fills catalog search when the modal opens (e.g. candidate display name). */
  initialSearchQuery?: string | null
  /** Omit from suggestions/search (e.g. canonical detail page the move was started from). */
  excludeCanonicalId?: string | null
}) {
  const { substrateLocationId, ...rest } = props
  return (
    <CanonicalLinkModalGeneric
      {...rest}
      substrateId={substrateLocationId}
      config={locationCanonicalLinkModalConfig}
    />
  )
}
