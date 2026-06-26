/** Core API project key scopes (`backfield_api_credential.scopes`). */
export type ProjectApiKeyScope = 'read' | 'runs:trigger'

export type ProjectApiKeyScopeOption = {
  id: ProjectApiKeyScope
  label: string
  description: string
  /** Always granted; shown checked and disabled in the UI. */
  required: boolean
  /** Only assignable on service (automation) keys. */
  serviceOnly: boolean
}

export const PROJECT_API_KEY_SCOPE_OPTIONS: ProjectApiKeyScopeOption[] = [
  {
    id: 'read',
    label: 'Read project data',
    description: 'Search articles, entities, and other read-only public API routes.',
    required: true,
    serviceOnly: false,
  },
  {
    id: 'runs:trigger',
    label: 'Trigger flows via API',
    description: 'Start Agate flows that have Enable API runs turned on.',
    required: false,
    serviceOnly: true,
  },
]

export function scopeOptionLabel(scope: string): string {
  const match = PROJECT_API_KEY_SCOPE_OPTIONS.find((option) => option.id === scope)
  return match?.label ?? scope
}

/** Scopes to send on key create; backend always includes `read`. */
export function scopesForCreateRequest(
  credentialType: 'user' | 'service',
  selected: ReadonlySet<ProjectApiKeyScope>,
): ProjectApiKeyScope[] | undefined {
  if (credentialType !== 'service' || !selected.has('runs:trigger')) {
    return undefined
  }
  return ['runs:trigger']
}

export function defaultCreateScopeSelection(): Set<ProjectApiKeyScope> {
  return new Set<ProjectApiKeyScope>(['read'])
}

export function normalizeScopeSelectionForType(
  credentialType: 'user' | 'service',
  selected: ReadonlySet<ProjectApiKeyScope>,
): Set<ProjectApiKeyScope> {
  const next = new Set<ProjectApiKeyScope>(['read'])
  if (credentialType === 'service' && selected.has('runs:trigger')) {
    next.add('runs:trigger')
  }
  return next
}
