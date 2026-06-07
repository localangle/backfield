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
 * - Workflow scope: `project_scope` if present, otherwise `project` (Agate links).
 * - Canonical evidence filter: `project` when set alone doubles as workflow scope;
 *   when both params are set, `project_scope` is workflow and `project` is filter only.
 */
export function useProjectCatalogScope() {
  const params = useParams<{ stylebookSlug?: string }>()
  const [searchParams] = useSearchParams()
  const fromRoute = (params.stylebookSlug ?? "").trim()
  const fromLegacyQuery =
    parseLegacyStylebookQuery(`?${searchParams.toString()}`) ?? ""
  const stylebookSlug = fromRoute || fromLegacyQuery

  const explicitWorkflowScope = searchParams.get("project_scope") ?? ""
  const projectParam = searchParams.get("project") ?? ""
  /** Review queue / dashboard / shell context */
  const projectScopeSlug = explicitWorkflowScope || projectParam
  /** Canonical list/detail evidence filter (`project` query key). */
  const projectFilterSlug = projectParam

  const catalogBasePath = useMemo(
    () => stylebookCatalogBasePath(stylebookSlug),
    [stylebookSlug],
  )

  const workflowScopeQueryString = useMemo(() => {
    const p = new URLSearchParams()
    if (!projectScopeSlug) return ""
    if (explicitWorkflowScope) {
      p.set("project_scope", projectScopeSlug)
    } else {
      p.set("project", projectScopeSlug)
    }
    return p.toString()
  }, [projectScopeSlug, explicitWorkflowScope])

  const filterScopeQueryString = useMemo(() => {
    const p = new URLSearchParams()
    if (projectFilterSlug) p.set("project", projectFilterSlug)
    return p.toString()
  }, [projectFilterSlug])

  const workflowScopeSuffix = workflowScopeQueryString
    ? `?${workflowScopeQueryString}`
    : ""
  const filterScopeSuffix = filterScopeQueryString ? `?${filterScopeQueryString}` : ""

  /** Full catalog query for cross-page links (workflow scope + optional evidence filter). */
  const catalogScopeQueryString = useMemo(() => {
    const p = new URLSearchParams()
    if (explicitWorkflowScope) p.set("project_scope", explicitWorkflowScope)
    if (projectParam) p.set("project", projectParam)
    return p.toString()
  }, [explicitWorkflowScope, projectParam])

  const catalogScopeSuffix = catalogScopeQueryString
    ? `?${catalogScopeQueryString}`
    : ""

  return {
    projectScopeSlug,
    projectFilterSlug,
    stylebookSlug,
    catalogBasePath,
    workflowScopeQueryString,
    workflowScopeSuffix,
    filterScopeQueryString,
    filterScopeSuffix,
    catalogScopeQueryString,
    catalogScopeSuffix,
  }
}
