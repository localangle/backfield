import { useMemo } from "react"
import { useProjectCatalogScope } from "@/lib/catalogNavigation"
import { useSelectedStylebookLabel } from "@/lib/stylebookScopeContext"

export function useScopeBreadcrumbRoot(): { label: string; to: string } {
  const { filterScopeSuffix } = useProjectCatalogScope()
  const label = useSelectedStylebookLabel()
  return useMemo(
    () => ({ label, to: `/${filterScopeSuffix}` }),
    [label, filterScopeSuffix],
  )
}

