import { CanonicalListPage } from "@/components/CanonicalListPage"
import { locationCanonicalListConfig } from "@/lib/entityConfigs/location/canonicalList"

export default function Locations() {
  return <CanonicalListPage config={locationCanonicalListConfig} />
}
