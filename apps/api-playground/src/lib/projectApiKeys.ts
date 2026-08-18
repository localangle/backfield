import {
  fetchProjectApiKeys,
  type PlatformProject,
} from "./session"

/** Currently selected secret. Migrated into the vault on first read after this ships. */
export const API_KEY_ACTIVE_SESSION_STORAGE = "backfield-playground-project-api-key"
export const API_KEY_VAULT_SESSION_STORAGE = "backfield-playground-project-api-keys"

/** Core stores `key_prefix = raw_key[:22]` and never returns the secret on list. */
export const PROJECT_API_KEY_PREFIX_LENGTH = 22

const DISPLAY_PREFIX_LENGTH = 10

export interface ProjectApiKeyMetadata {
  prefix: string
  label: string | null
  projectId: number
  projectName: string
  projectSlug: string
}

export function projectApiKeyPrefix(secret: string): string {
  return secret.trim().slice(0, PROJECT_API_KEY_PREFIX_LENGTH)
}

function uniqueNonEmptySecrets(secrets: string[]): string[] {
  const seen = new Set<string>()
  const unique: string[] = []
  for (const secret of secrets) {
    const trimmed = secret.trim()
    if (!trimmed || seen.has(trimmed)) continue
    seen.add(trimmed)
    unique.push(trimmed)
  }
  return unique
}

export function readRememberedApiKeys(): string[] {
  try {
    const raw = sessionStorage.getItem(API_KEY_VAULT_SESSION_STORAGE)
    if (raw) {
      const parsed: unknown = JSON.parse(raw)
      if (Array.isArray(parsed)) {
        return uniqueNonEmptySecrets(
          parsed.filter((item): item is string => typeof item === "string"),
        )
      }
    }
    const legacy = sessionStorage.getItem(API_KEY_ACTIVE_SESSION_STORAGE)?.trim()
    return legacy ? [legacy] : []
  } catch {
    return []
  }
}

export function writeRememberedApiKeys(secrets: string[]): void {
  try {
    const unique = uniqueNonEmptySecrets(secrets)
    if (!unique.length) {
      sessionStorage.removeItem(API_KEY_VAULT_SESSION_STORAGE)
      return
    }
    sessionStorage.setItem(API_KEY_VAULT_SESSION_STORAGE, JSON.stringify(unique))
  } catch {
    // Storage may be unavailable; the vault remains in memory for this page.
  }
}

export function rememberApiKey(secret: string, current: string[]): string[] {
  return uniqueNonEmptySecrets([...current, secret])
}

export function forgetAllProjectApiKeys(): void {
  try {
    sessionStorage.removeItem(API_KEY_VAULT_SESSION_STORAGE)
    sessionStorage.removeItem(API_KEY_ACTIVE_SESSION_STORAGE)
  } catch {
    // In-memory state is still cleared by callers.
  }
}

function displayPrefix(prefix: string): string {
  if (prefix.length <= DISPLAY_PREFIX_LENGTH) return `${prefix}…`
  return `${prefix.slice(0, DISPLAY_PREFIX_LENGTH)}…`
}

export function displayLabelForSecret(
  secret: string,
  metadata: ProjectApiKeyMetadata[],
): string {
  const prefix = projectApiKeyPrefix(secret)
  const shortPrefix = displayPrefix(prefix)
  const match = metadata.find((row) => row.prefix === prefix)
  if (!match) return shortPrefix
  const name = match.label?.trim()
  if (name) return `${match.projectName} — ${name} (${shortPrefix})`
  return `${match.projectName} (${shortPrefix})`
}

export function secretForPrefix(
  secrets: string[],
  prefix: string,
): string | undefined {
  return secrets.find((secret) => projectApiKeyPrefix(secret) === prefix)
}

export async function fetchAccessibleProjectApiKeyMetadata(
  sessionOrigin: string,
  projects: PlatformProject[],
): Promise<ProjectApiKeyMetadata[]> {
  const lists = await Promise.all(
    projects.map(async (project) => {
      try {
        const rows = await fetchProjectApiKeys(sessionOrigin, project.id)
        const labeled: ProjectApiKeyMetadata[] = []
        for (const row of rows) {
          const prefix = row.key_prefix?.trim()
          if (!prefix || row.revoked_at) continue
          labeled.push({
            prefix,
            label: row.label?.trim() || null,
            projectId: project.id,
            projectName: project.name,
            projectSlug: project.slug,
          })
        }
        return labeled
      } catch {
        return []
      }
    }),
  )
  return lists.flat()
}
