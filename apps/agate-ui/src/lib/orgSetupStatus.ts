import type { AiCredentialCatalogEntry, IntegrationSecretMetadata } from '@/lib/core-api'
import { PLATFORM_INTEGRATION_KEYS } from '@/lib/platform-integration-keys'

export function hasConfiguredAiCredentials(entries: AiCredentialCatalogEntry[]): boolean {
  return entries.some((entry) => entry.configured)
}

export function hasConfiguredPlatformIntegrations(
  metadata: IntegrationSecretMetadata[],
): boolean {
  const allowed = new Set<string>(Object.values(PLATFORM_INTEGRATION_KEYS))
  return metadata.some((row) => allowed.has(row.integration_key))
}

/** True when the org has not saved any model keys or platform integrations yet. */
export function isOrganizationSetupIncomplete(input: {
  aiCredentials: AiCredentialCatalogEntry[]
  integrationMetadata: IntegrationSecretMetadata[]
}): boolean {
  return (
    !hasConfiguredAiCredentials(input.aiCredentials) &&
    !hasConfiguredPlatformIntegrations(input.integrationMetadata)
  )
}
