/** Core API project key scopes (`backfield_api_credential.scopes`). */
export type ProjectApiKeyScope = 'read' | 'runs:trigger' | 'cleanup:read' | 'cleanup:apply'

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
  {
    id: 'cleanup:read',
    label: 'Read Stylebook data for cleanup (preview)',
    description: 'Let a cleanup tool look through Stylebook records, evidence, and review queues.',
    required: false,
    serviceOnly: false,
  },
  {
    id: 'cleanup:apply',
    label: 'Make Stylebook cleanup changes (preview)',
    description:
      'Let an automated cleanup tool merge, edit, and remove Stylebook records. Includes reading for cleanup.',
    required: false,
    serviceOnly: true,
  },
]

function isAllowedForType(scope: ProjectApiKeyScope, credentialType: 'user' | 'service'): boolean {
  const option = PROJECT_API_KEY_SCOPE_OPTIONS.find((candidate) => candidate.id === scope)
  return option !== undefined && (credentialType === 'service' || !option.serviceOnly)
}

/** Selected scopes allowed for the key type, in display order; cleanup changes include cleanup reading. */
function allowedExtraScopes(
  credentialType: 'user' | 'service',
  selected: ReadonlySet<string>,
): ProjectApiKeyScope[] {
  return PROJECT_API_KEY_SCOPE_OPTIONS.filter(
    (option) =>
      !option.required &&
      isAllowedForType(option.id, credentialType) &&
      (selected.has(option.id) ||
        (option.id === 'cleanup:read' &&
          credentialType === 'service' &&
          selected.has('cleanup:apply'))),
  ).map((option) => option.id)
}

export function scopeOptionLabel(scope: string): string {
  const match = PROJECT_API_KEY_SCOPE_OPTIONS.find((option) => option.id === scope)
  return match?.label ?? scope
}

/** Scopes to send on key create; backend always includes `read`. */
export function scopesForCreateRequest(
  credentialType: 'user' | 'service',
  selected: ReadonlySet<ProjectApiKeyScope>,
): ProjectApiKeyScope[] | undefined {
  const extras = allowedExtraScopes(credentialType, selected)
  return extras.length > 0 ? extras : undefined
}

/** Scopes to send when rotating a key, so the new key keeps what the old one could do. */
export function scopesForRotation(
  credentialType: 'user' | 'service',
  existingScopes: readonly string[] | undefined,
): ProjectApiKeyScope[] | undefined {
  return scopesForCreateRequest(
    credentialType,
    new Set((existingScopes ?? []) as ProjectApiKeyScope[]),
  )
}

export function defaultCreateScopeSelection(): Set<ProjectApiKeyScope> {
  return new Set<ProjectApiKeyScope>(['read'])
}

export function normalizeScopeSelectionForType(
  credentialType: 'user' | 'service',
  selected: ReadonlySet<ProjectApiKeyScope>,
): Set<ProjectApiKeyScope> {
  return new Set<ProjectApiKeyScope>(['read', ...allowedExtraScopes(credentialType, selected)])
}
