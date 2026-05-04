import { useMemo } from "react"
import { useSearchParams } from "react-router-dom"
import { STYLEBOOK_URL_QUERY_KEY } from "@/lib/stylebook-api/client"

/**
 * Reads/writes project + catalog scope from the URL (same-origin as Stylebook API augmentation).
 */
export function useProjectCatalogScope() {
  const [searchParams] = useSearchParams()
  const projectSlug = searchParams.get("project") ?? ""
  const stylebookSlug = searchParams.get(STYLEBOOK_URL_QUERY_KEY) ?? ""

  const scopeQueryString = useMemo(() => {
    const p = new URLSearchParams()
    if (projectSlug) p.set("project", projectSlug)
    if (stylebookSlug) p.set(STYLEBOOK_URL_QUERY_KEY, stylebookSlug)
    return p.toString()
  }, [projectSlug, stylebookSlug])

  const scopeSuffix = scopeQueryString ? `?${scopeQueryString}` : ""

  return {
    projectSlug,
    stylebookSlug,
    scopeQueryString,
    scopeSuffix,
  }
}
