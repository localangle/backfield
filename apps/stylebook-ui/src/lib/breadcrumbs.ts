import { useMemo } from "react"
import { useProjectCatalogScope } from "@/lib/catalogNavigation"
import { useSelectedStylebookLabel } from "@/lib/stylebookScopeContext"

export function useScopeBreadcrumbRoot(): { label: string; to: string } {
  const { scopeSuffix } = useProjectCatalogScope()
  const label = useSelectedStylebookLabel()
  return useMemo(() => ({ label, to: `/${scopeSuffix}` }), [label, scopeSuffix])
}

