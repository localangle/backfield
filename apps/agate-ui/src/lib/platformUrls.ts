/** Cross-app navigation (Agate ↔ Stylebook SPAs). */

import { resolveUiOrigin } from '@backfield/ui/siblingUiOrigin'

function browserOrigin(): string {
  if (typeof window !== 'undefined') {
    return window.location.origin
  }
  return ''
}

export function agateUiOrigin(): string {
  return resolveUiOrigin({
    envOverride: import.meta.env.VITE_AGATE_UI_ORIGIN,
    currentOrigin: browserOrigin(),
    targetApp: 'agate',
  })
}

export function stylebookUiOrigin(): string {
  return resolveUiOrigin({
    envOverride: import.meta.env.VITE_STYLEBOOK_UI_ORIGIN,
    currentOrigin: browserOrigin(),
    targetApp: 'stylebook',
  })
}

/** External docs or fallback to Agate `/help`. */
export function helpHref(): string {
  const raw = import.meta.env.VITE_HELP_URL
  if (typeof raw === 'string' && raw.trim() !== '') {
    return raw.trim()
  }
  return `${agateUiOrigin()}/help`
}

/** Standalone API Playground, with an explicit local-development target. */
export function playgroundHref(): string {
  const override = import.meta.env.VITE_PLAYGROUND_URL
  if (typeof override === 'string' && override.trim() !== '') {
    return override.trim()
  }
  const origin = browserOrigin()
  if (origin) {
    const url = new URL(origin)
    if (url.hostname === 'localhost' || url.hostname === '127.0.0.1') {
      return `${url.protocol}//${url.hostname}:5176`
    }
  }
  return 'https://playground.backfield.news'
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
