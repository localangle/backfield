import type {
  ConfirmChoice,
  ShowAppConfirmChoiceOptions,
  ShowAppConfirmOptions,
} from '@/components/AppMessageProvider'

export const RERUN_WARNING_TITLE = 'Rerun item?'

export const RUN_AGAIN_WARNING_TITLE = 'Replay run?'

export const RERUN_ORIGINAL_FLOW_LABEL = 'Rerun original flow'

export const RUN_UPDATED_FLOW_LABEL = 'Run updated flow'

export type ReconciliationPolicy = 'add_only' | 'smart_merge' | 'replace'

export type FlowRerunDecision = 'original' | 'updated' | false

type FlowWarningOptions = {
  flowName?: string | null
  policy?: ReconciliationPolicy | string | null
  /** When true, mention that Run updated flow uses the current saved flow. */
  offerUpdatedFlow?: boolean
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

export function shouldOfferUpdatedFlow(
  flowChanged: boolean | null | undefined,
): boolean {
  return flowChanged === true
}

const flowSentence = ({ flowName, policy }: FlowWarningOptions): string => {
  const quoted = flowName?.trim() ? `“${flowName.trim()}”` : 'this flow'
  const normalized = normalizeReconciliationPolicy(policy)
  return (
    `This will replay using the flow settings from when this run started` +
    (quoted ? ` (${quoted})` : '') +
    ` with ${policyLabel(normalized)}.`
  )
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

const updatedFlowSentence = 'Run updated flow uses the current saved flow.'

export const RUN_AGAIN_WARNING_BODY =
  flowSentence({ policy: 'smart_merge' }) + ' ' + policySentence('smart_merge')

export const runAgainWarningBody = (options: FlowWarningOptions = {}): string => {
  const policy = normalizeReconciliationPolicy(options.policy)
  const body = `${flowSentence({ ...options, policy })} ${policySentence(policy)}`
  if (!options.offerUpdatedFlow) return body
  return `${body} ${updatedFlowSentence}`
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
  const body = `${flowSentence({ ...options, policy })} Run review edits on ${itemPhrase} will be cleared. ${policySentence(policy)}`
  if (!options.offerUpdatedFlow) return body
  return `${body} ${updatedFlowSentence}`
}

export async function promptFlowRerun(args: {
  flowChanged: boolean | null | undefined
  title: string
  unchangedConfirmLabel: string
  description: string
  originalPolicy: ReconciliationPolicy
  updatedPolicy: ReconciliationPolicy
  showConfirm: (description: string, options?: ShowAppConfirmOptions) => Promise<boolean>
  showConfirmChoice: (
    description: string,
    options: ShowAppConfirmChoiceOptions,
  ) => Promise<ConfirmChoice>
}): Promise<FlowRerunDecision> {
  if (!shouldOfferUpdatedFlow(args.flowChanged)) {
    const ok = await args.showConfirm(args.description, {
      title: args.title,
      confirmLabel: args.unchangedConfirmLabel,
      destructive: args.originalPolicy === 'replace',
    })
    return ok ? 'original' : false
  }
  const choice = await args.showConfirmChoice(args.description, {
    title: args.title,
    primaryLabel: RERUN_ORIGINAL_FLOW_LABEL,
    secondaryLabel: RUN_UPDATED_FLOW_LABEL,
    primaryDestructive: args.originalPolicy === 'replace',
    secondaryDestructive: args.updatedPolicy === 'replace',
  })
  if (choice === 'primary') return 'original'
  if (choice === 'secondary') return 'updated'
  return false
}
