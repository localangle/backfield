/** Cross-app navigation (Agate ↔ Stylebook SPAs). */

export function agateUiOrigin(): string {
  const raw = import.meta.env.VITE_AGATE_UI_ORIGIN
  if (typeof raw === 'string' && raw.trim() !== '') {
    return raw.trim().replace(/\/$/, '')
  }
  return 'http://localhost:5173'
}

export function stylebookUiOrigin(): string {
  const raw = import.meta.env.VITE_STYLEBOOK_UI_ORIGIN
  if (typeof raw === 'string' && raw.trim() !== '') {
    return raw.trim().replace(/\/$/, '')
  }
  return typeof window !== 'undefined' ? window.location.origin : 'http://localhost:5175'
}

export function helpHref(): string {
  const raw = import.meta.env.VITE_HELP_URL
  if (typeof raw === 'string' && raw.trim() !== '') {
    return raw.trim()
  }
  return `${agateUiOrigin()}/help`
}

/** Agate SPA project home (flows, runs, settings). */
export function agateProjectHref(projectSlug: string): string {
  const base = agateUiOrigin().replace(/\/$/, '')
  return `${base}/project/${encodeURIComponent(projectSlug)}`
}

/** Agate SPA workspace hub. */
export function agateWorkspaceHref(workspaceSlug: string): string {
  const base = agateUiOrigin().replace(/\/$/, '')
  return `${base}/workspace/${encodeURIComponent(workspaceSlug)}`
}
