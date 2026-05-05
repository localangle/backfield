import { useMemo } from "react"
import { useSearchParams } from "react-router-dom"
import { STYLEBOOK_URL_QUERY_KEY } from "@/lib/stylebook-api/client"

/**
 * Reads/writes URL scope for Stylebook UI.
 *
 * - `project_scope`: required for project-scoped workflows (review queue, etc.)
 * - `project`: optional evidence filter on stylebook-scoped canonical pages
 * - `stylebook`: selected org stylebook (stable slug)
 */
export function useProjectCatalogScope() {
  const [searchParams] = useSearchParams()
  const projectScopeSlug = searchParams.get("project_scope") ?? ""
  const projectFilterSlug = searchParams.get("project") ?? ""
  const stylebookSlug = searchParams.get(STYLEBOOK_URL_QUERY_KEY) ?? ""

  const workflowScopeQueryString = useMemo(() => {
    const p = new URLSearchParams()
    if (projectScopeSlug) p.set("project_scope", projectScopeSlug)
    if (stylebookSlug) p.set(STYLEBOOK_URL_QUERY_KEY, stylebookSlug)
    return p.toString()
  }, [projectScopeSlug, stylebookSlug])

  const filterScopeQueryString = useMemo(() => {
    const p = new URLSearchParams()
    if (projectFilterSlug) p.set("project", projectFilterSlug)
    if (stylebookSlug) p.set(STYLEBOOK_URL_QUERY_KEY, stylebookSlug)
    return p.toString()
  }, [projectFilterSlug, stylebookSlug])

  const workflowScopeSuffix = workflowScopeQueryString
    ? `?${workflowScopeQueryString}`
    : ""
  const filterScopeSuffix = filterScopeQueryString ? `?${filterScopeQueryString}` : ""

  return {
    projectScopeSlug,
    projectFilterSlug,
    stylebookSlug,
    workflowScopeQueryString,
    workflowScopeSuffix,
    filterScopeQueryString,
    filterScopeSuffix,
  }
}
