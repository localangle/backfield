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

/** Stylebook UI URL with project + stylebook slug query. */
export function stylebookShellHref(projectSlug: string, stylebookSlug: string): string {
  const base = stylebookUiOrigin()
  const q = new URLSearchParams()
  q.set('project', projectSlug)
  q.set('stylebook', stylebookSlug)
  return `${base}/?${q.toString()}`
}
