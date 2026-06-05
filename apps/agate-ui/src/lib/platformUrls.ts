/** Cross-app navigation (Agate ↔ Stylebook SPAs). */

export function agateUiOrigin(): string {
  const raw = import.meta.env.VITE_AGATE_UI_ORIGIN
  if (typeof raw === 'string' && raw.trim() !== '') {
    return raw.trim().replace(/\/$/, '')
  }
  return typeof window !== 'undefined' ? window.location.origin : 'http://localhost:5173'
}

export function stylebookUiOrigin(): string {
  const raw = import.meta.env.VITE_STYLEBOOK_UI_ORIGIN
  if (typeof raw === 'string' && raw.trim() !== '') {
    return raw.trim().replace(/\/$/, '')
  }
  return 'http://localhost:5175'
}

/** External docs or fallback to Agate `/help`. */
export function helpHref(): string {
  const raw = import.meta.env.VITE_HELP_URL
  if (typeof raw === 'string' && raw.trim() !== '') {
    return raw.trim()
  }
  return `${agateUiOrigin()}/help`
}

/**
 * Stylebook UI URL: `/stylebook/<slug>/`. Optionally adds Agate project context as
 * `?project=<slug>` (same query key Stylebook uses for workflow scope when
 * `project_scope` is omitted). Legacy `/?stylebook=` still redirects on load.
 */
export function stylebookShellHref(
  stylebookSlug: string,
  projectSlug?: string | null,
): string {
  const base = stylebookUiOrigin().replace(/\/$/, '')
  const path = `/stylebook/${encodeURIComponent(stylebookSlug)}`
  const q = new URLSearchParams()
  if (projectSlug) {
    q.set('project', projectSlug)
  }
  const qs = q.toString()
  return `${base}${path}${qs ? `?${qs}` : ''}`
}

/**
 * Stylebook catalog canonical list with optional search query (reads ``q`` on the Locations page).
 */
export function stylebookCanonicalListHref(
  stylebookSlug: string,
  opts: { projectSlug?: string | null; searchQuery?: string | null },
): string {
  const shell = stylebookShellHref(stylebookSlug, opts.projectSlug ?? undefined)
  const url = new URL(shell)
  const root = url.pathname.replace(/\/$/, '')
  url.pathname = `${root}/locations/canonical`
  if (opts.searchQuery && opts.searchQuery.trim()) {
    url.searchParams.set('q', opts.searchQuery.trim().slice(0, 200))
  }
  return url.toString()
}

/** Open a specific catalog place (canonical UUID) in Stylebook. */
export function stylebookCanonicalDetailHref(
  stylebookSlug: string,
  canonicalId: string,
  projectSlug?: string | null,
): string {
  const shell = stylebookShellHref(stylebookSlug, projectSlug ?? undefined)
  const url = new URL(shell)
  const root = url.pathname.replace(/\/$/, '')
  url.pathname = `${root}/locations/canonical/${encodeURIComponent(canonicalId)}`
  return url.toString()
}

/** Open a specific catalog person (canonical UUID) in Stylebook. */
export function stylebookPersonCanonicalDetailHref(
  stylebookSlug: string,
  canonicalId: string,
  projectSlug?: string | null,
): string {
  const shell = stylebookShellHref(stylebookSlug, projectSlug ?? undefined)
  const url = new URL(shell)
  const root = url.pathname.replace(/\/$/, '')
  url.pathname = `${root}/people/canonical/${encodeURIComponent(canonicalId)}`
  return url.toString()
}

/** Stylebook people candidate queue for this project. */
export function stylebookPeopleCandidatesHref(
  stylebookSlug: string,
  projectSlug?: string | null,
): string {
  const shell = stylebookShellHref(stylebookSlug, projectSlug ?? undefined)
  const url = new URL(shell)
  const root = url.pathname.replace(/\/$/, '')
  url.pathname = `${root}/people/candidates`
  return url.toString()
}

/** Open a specific catalog organization (canonical UUID) in Stylebook. */
export function stylebookOrganizationCanonicalDetailHref(
  stylebookSlug: string,
  canonicalId: string,
  projectSlug?: string | null,
): string {
  const shell = stylebookShellHref(stylebookSlug, projectSlug ?? undefined)
  const url = new URL(shell)
  const root = url.pathname.replace(/\/$/, '')
  url.pathname = `${root}/organizations/canonical/${encodeURIComponent(canonicalId)}`
  return url.toString()
}

/** Stylebook organizations candidate queue for this project. */
export function stylebookOrganizationsCandidatesHref(
  stylebookSlug: string,
  projectSlug?: string | null,
): string {
  const shell = stylebookShellHref(stylebookSlug, projectSlug ?? undefined)
  const url = new URL(shell)
  const root = url.pathname.replace(/\/$/, '')
  url.pathname = `${root}/organizations/candidates`
  return url.toString()
}
