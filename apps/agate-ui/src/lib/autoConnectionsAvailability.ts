/** Eligibility helpers for Backfield Output automatic connections (panel gating). */

export type AutoConnectionsIneligibleReason =
  | 'stylebook_matching_off'
  | 'rules_only'
  | 'auto_apply_off'

export interface AutoConnectionsPanelParams {
  stylebook_matching_enabled: boolean
  canonicalization_mode: string
  auto_apply_canonicalization: boolean
}

export function autoConnectionsEligibility(
  params: AutoConnectionsPanelParams,
): { eligible: boolean; reason: AutoConnectionsIneligibleReason | null } {
  if (!params.stylebook_matching_enabled) {
    return { eligible: false, reason: 'stylebook_matching_off' }
  }
  if (params.canonicalization_mode !== 'ai_assisted') {
    return { eligible: false, reason: 'rules_only' }
  }
  if (!params.auto_apply_canonicalization) {
    return { eligible: false, reason: 'auto_apply_off' }
  }
  return { eligible: true, reason: null }
}

export function autoConnectionsIneligibleCopy(
  reason: AutoConnectionsIneligibleReason | null,
): string {
  switch (reason) {
    case 'stylebook_matching_off':
      return 'Turn on Stylebook matching in Settings to use automatic connections.'
    case 'rules_only':
      return 'Available when matching strategy is AI Assisted.'
    case 'auto_apply_off':
      return 'Available when auto-apply matching is on.'
    default:
      return ''
  }
}

/** Whether the automatic connections select should be interactive. */
export function autoConnectionsSelectDisabled(
  eligible: boolean,
  panelDisabled: boolean,
): boolean {
  return panelDisabled || !eligible
}

/** Yes/no display value for the automatic connections select. */
export function autoConnectionsUiShowsYes(eligible: boolean, enabled: boolean): boolean {
  return eligible && enabled
}

/** Default-on for new eligible nodes when the param is unset. */
export function resolvedAutoConnectionsEnabled(
  raw: boolean | undefined | null,
): boolean {
  return raw !== false
}
