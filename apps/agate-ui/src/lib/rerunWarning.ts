/** Confirmation copy for re-runs that use the current saved flow. */

export const RERUN_WARNING_TITLE = 'Rerun item?'

export const RUN_AGAIN_WARNING_TITLE = 'Rerun all items?'

export type ReconciliationPolicy = 'add_only' | 'smart_merge' | 'replace'

type FlowWarningOptions = {
  flowName?: string | null
  policy?: ReconciliationPolicy | string | null
}

const policyLabel = (policy: ReconciliationPolicy): string => {
  if (policy === 'add_only') return 'Add Only'
  if (policy === 'replace') return 'Replace'
  return 'Smart Merge'
}

export const normalizeReconciliationPolicy = (
  policy: ReconciliationPolicy | string | null | undefined,
): ReconciliationPolicy => {
  if (policy === 'add_only' || policy === 'replace' || policy === 'smart_merge') {
    return policy
  }
  return 'smart_merge'
}

export const reconciliationPolicyFromGraph = (graph: {
  spec?: { nodes?: Array<{ type?: string; params?: Record<string, unknown> }> }
} | null): ReconciliationPolicy => {
  const node = graph?.spec?.nodes?.find((n) => n.type === 'DBOutput')
  return normalizeReconciliationPolicy(node?.params?.reconciliation_policy as string | undefined)
}

const flowSentence = ({ flowName, policy }: FlowWarningOptions): string => {
  const quoted = flowName?.trim() ? `“${flowName.trim()}”` : 'this flow'
  const normalized = normalizeReconciliationPolicy(policy)
  return `This will use the current saved version of ${quoted} with ${policyLabel(normalized)}.`
}

const policySentence = (policy: ReconciliationPolicy): string => {
  if (policy === 'add_only') {
    return 'It will add new saved data from the flow without changing existing saved data.'
  }
  if (policy === 'replace') {
    return 'It will replace existing saved data from the flow’s categories with this run’s results.'
  }
  return 'It will update saved data from the flow while preserving changes made by editors.'
}

export const RUN_AGAIN_WARNING_BODY = flowSentence({ policy: 'smart_merge' }) + ' ' + policySentence('smart_merge')

export const runAgainWarningBody = (options: FlowWarningOptions = {}): string => {
  const policy = normalizeReconciliationPolicy(options.policy)
  return `${flowSentence({ ...options, policy })} ${policySentence(policy)}`
}

export const rerunWarningTitle = (itemCount = 1): string =>
  itemCount === 1 ? RERUN_WARNING_TITLE : 'Rerun items?'

export const rerunWarningBody = (
  itemCount = 1,
  options: FlowWarningOptions = {},
): string => {
  const itemPhrase =
    itemCount === 1 ? 'this item' : `these ${itemCount} items`
  const policy = normalizeReconciliationPolicy(options.policy)
  return `${flowSentence({ ...options, policy })} Run review edits on ${itemPhrase} will be cleared. ${policySentence(policy)}`
}
