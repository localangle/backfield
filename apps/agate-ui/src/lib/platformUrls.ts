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
