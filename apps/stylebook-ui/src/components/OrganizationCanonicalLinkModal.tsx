import { CanonicalLinkModalGeneric } from "@/components/CanonicalLinkModalGeneric"
import { organizationCanonicalLinkModalConfig } from "@/lib/entityConfigs/organization/canonicalLinkModal"

export function OrganizationCanonicalLinkModal(props: {
  open: boolean
  onOpenChange: (open: boolean) => void
  projectSlug: string
  stylebookSlug: string
  substrateOrganizationId: number | null
  onDone: () => void
  onLinked?: (canonical: { id: string; label: string }) => void
  title?: string
  initialCanonicalId?: string | null
  /** Pre-fills catalog search when the modal opens (e.g. candidate display name). */
  initialSearchQuery?: string | null
  /** Omit from suggestions/search (e.g. canonical detail page the move was started from). */
  excludeCanonicalId?: string | null
}) {
  const { substrateOrganizationId, ...rest } = props
  return (
    <CanonicalLinkModalGeneric
      {...rest}
      substrateId={substrateOrganizationId}
      config={organizationCanonicalLinkModalConfig}
    />
  )
}
