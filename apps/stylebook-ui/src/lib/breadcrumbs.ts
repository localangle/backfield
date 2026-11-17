import { useMemo } from "react"
import { useProjectCatalogScope } from "@/lib/catalogNavigation"
import { useSelectedStylebookLabel } from "@/lib/stylebookScopeContext"

export function useScopeBreadcrumbRoot(): { label: string; to: string } {
  // The catalog home is a workflow page, so the link keeps the project scope (not the evidence filter).
  const { catalogBasePath, workflowScopeSuffix } = useProjectCatalogScope()
  const label = useSelectedStylebookLabel()
  return useMemo(
    () => ({ label, to: `${catalogBasePath}${workflowScopeSuffix}` }),
    [label, catalogBasePath, workflowScopeSuffix],
  )
}

