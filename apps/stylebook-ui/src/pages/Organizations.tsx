import { CanonicalListPage } from "@/components/CanonicalListPage"
import { organizationCanonicalListConfig } from "@/lib/entityConfigs/organization/canonicalList"

export default function Organizations() {
  return <CanonicalListPage config={organizationCanonicalListConfig} />
}
