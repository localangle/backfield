import { CanonicalListPage } from "@/components/CanonicalListPage"
import { personCanonicalListConfig } from "@/lib/entityConfigs/person/canonicalList"

export default function People() {
  return <CanonicalListPage config={personCanonicalListConfig} />
}
