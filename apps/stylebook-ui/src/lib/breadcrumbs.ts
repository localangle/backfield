import { useMemo } from "react"
import { useProjectCatalogScope } from "@/lib/catalogNavigation"
import { useSelectedStylebookLabel } from "@/lib/stylebookScopeContext"

export function useScopeBreadcrumbRoot(): { label: string; to: string } {
  const { catalogBasePath, filterScopeSuffix } = useProjectCatalogScope()
  const label = useSelectedStylebookLabel()
  return useMemo(
    () => ({ label, to: `${catalogBasePath}${filterScopeSuffix}` }),
    [label, catalogBasePath, filterScopeSuffix],
  )
}

