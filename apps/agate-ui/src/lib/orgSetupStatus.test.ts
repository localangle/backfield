import { describe, expect, it } from 'vitest'

import type { AiCredentialCatalogEntry, IntegrationSecretMetadata } from '@/lib/core-api'
import { PLATFORM_INTEGRATION_KEYS } from '@/lib/platform-integration-keys'
import {
  hasConfiguredAiCredentials,
  hasConfiguredPlatformIntegrations,
  isOrganizationSetupIncomplete,
} from '@/lib/orgSetupStatus'

function aiCredential(configured: boolean): AiCredentialCatalogEntry {
  return {
    integration_secret_id: configured ? 1 : null,
    integration_key: 'ai.openai',
    credential_kind: 'preset',
    provider: 'openai',
    configured,
    has_api_base: false,
    linked_catalog_models: [],
    created_at: null,
    updated_at: null,
  }
}

function integrationRow(integrationKey: string): IntegrationSecretMetadata {
  return {
    integration_key: integrationKey,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  }
}

describe('orgSetupStatus', () => {
  it('detects configured AI credentials', () => {
    expect(hasConfiguredAiCredentials([aiCredential(false)])).toBe(false)
    expect(hasConfiguredAiCredentials([aiCredential(true)])).toBe(true)
  })

  it('detects configured platform integrations', () => {
    expect(hasConfiguredPlatformIntegrations([])).toBe(false)
    expect(
      hasConfiguredPlatformIntegrations([
        integrationRow('custom.unrelated'),
        integrationRow(PLATFORM_INTEGRATION_KEYS.geocodio),
      ]),
    ).toBe(true)
  })

  it('marks setup incomplete only when both areas are empty', () => {
    expect(
      isOrganizationSetupIncomplete({
        aiCredentials: [aiCredential(false)],
        integrationMetadata: [],
      }),
    ).toBe(true)

    expect(
      isOrganizationSetupIncomplete({
        aiCredentials: [aiCredential(true)],
        integrationMetadata: [],
      }),
    ).toBe(false)

    expect(
      isOrganizationSetupIncomplete({
        aiCredentials: [],
        integrationMetadata: [integrationRow(PLATFORM_INTEGRATION_KEYS.braveSearch)],
      }),
    ).toBe(false)
  })
})
