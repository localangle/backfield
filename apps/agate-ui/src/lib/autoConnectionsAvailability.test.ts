import { describe, expect, it } from 'vitest'
import {
  autoConnectionsEligibility,
  autoConnectionsIneligibleCopy,
  autoConnectionsSelectDisabled,
  autoConnectionsUiShowsYes,
  resolvedAutoConnectionsEnabled,
} from './autoConnectionsAvailability'

describe('autoConnectionsAvailability helpers', () => {
  const eligibleParams = {
    stylebook_matching_enabled: true,
    canonicalization_mode: 'ai_assisted',
    auto_apply_canonicalization: true,
  }

  it('treats unset auto_connections_enabled as on by default', () => {
    expect(resolvedAutoConnectionsEnabled(undefined)).toBe(true)
    expect(resolvedAutoConnectionsEnabled(null)).toBe(true)
    expect(resolvedAutoConnectionsEnabled(false)).toBe(false)
  })

  it('marks eligible when stylebook AI-assisted auto-apply is on', () => {
    expect(autoConnectionsEligibility(eligibleParams)).toEqual({
      eligible: true,
      reason: null,
    })
  })

  it('blocks when stylebook matching is off', () => {
    const result = autoConnectionsEligibility({
      ...eligibleParams,
      stylebook_matching_enabled: false,
    })
    expect(result.eligible).toBe(false)
    expect(result.reason).toBe('stylebook_matching_off')
    expect(autoConnectionsIneligibleCopy(result.reason)).toContain('Stylebook matching')
  })

  it('blocks when canonicalization is rules-only', () => {
    const result = autoConnectionsEligibility({
      ...eligibleParams,
      canonicalization_mode: 'rules',
    })
    expect(result.reason).toBe('rules_only')
  })

  it('blocks when auto-apply is off', () => {
    const result = autoConnectionsEligibility({
      ...eligibleParams,
      auto_apply_canonicalization: false,
    })
    expect(result.reason).toBe('auto_apply_off')
  })

  it('disables select when ineligible', () => {
    expect(autoConnectionsSelectDisabled(false, false)).toBe(true)
    expect(autoConnectionsSelectDisabled(true, true)).toBe(true)
    expect(autoConnectionsSelectDisabled(true, false)).toBe(false)
  })

  it('shows Yes only when eligible and enabled', () => {
    expect(autoConnectionsUiShowsYes(true, true)).toBe(true)
    expect(autoConnectionsUiShowsYes(false, true)).toBe(false)
    expect(autoConnectionsUiShowsYes(true, false)).toBe(false)
  })
})
