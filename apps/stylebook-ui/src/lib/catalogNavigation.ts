import { useMemo } from "react"
import { useParams, useSearchParams } from "react-router-dom"
import {
  parseLegacyStylebookQuery,
  stylebookCatalogBasePath,
} from "@/lib/stylebookPaths"

/**
 * Reads URL scope for Stylebook UI.
 *
 * - Path `/stylebook/<slug>/…` selects the catalog (preferred).
 * - `project_scope`: workflows such as the review queue
 * - `project`: optional evidence filter on canonical pages
 */
export function useProjectCatalogScope() {
  const params = useParams<{ stylebookSlug?: string }>()
  const [searchParams] = useSearchParams()
  const fromRoute = (params.stylebookSlug ?? "").trim()
  const fromLegacyQuery =
    parseLegacyStylebookQuery(`?${searchParams.toString()}`) ?? ""
  const stylebookSlug = fromRoute || fromLegacyQuery

  const projectScopeSlug = searchParams.get("project_scope") ?? ""
  const projectFilterSlug = searchParams.get("project") ?? ""

  const catalogBasePath = useMemo(
    () => stylebookCatalogBasePath(stylebookSlug),
    [stylebookSlug],
  )

  const workflowScopeQueryString = useMemo(() => {
    const p = new URLSearchParams()
    if (projectScopeSlug) p.set("project_scope", projectScopeSlug)
    return p.toString()
  }, [projectScopeSlug])

  const filterScopeQueryString = useMemo(() => {
    const p = new URLSearchParams()
    if (projectFilterSlug) p.set("project", projectFilterSlug)
    return p.toString()
  }, [projectFilterSlug])

  const workflowScopeSuffix = workflowScopeQueryString
    ? `?${workflowScopeQueryString}`
    : ""
  const filterScopeSuffix = filterScopeQueryString ? `?${filterScopeQueryString}` : ""

  return {
    projectScopeSlug,
    projectFilterSlug,
    stylebookSlug,
    catalogBasePath,
    workflowScopeQueryString,
    workflowScopeSuffix,
    filterScopeQueryString,
    filterScopeSuffix,
  }
}
