import { isJsonInputInvalidNodeData, isValidJsonInputData } from '@/lib/jsonInputValidation'
import { isValidS3BucketName, s3BucketFieldError } from '@/lib/s3InputValidation'

export type FlowBuilderStep = 'input' | 'output' | 'scaffold'

export const FLOW_BUILDER_STEPS: FlowBuilderStep[] = ['input', 'output', 'scaffold']

export const STEP_HEADINGS: Record<FlowBuilderStep, string> = {
  input: 'Choose a source',
  output: 'Choose a destination',
  scaffold: 'Build your flow',
}

export const STEP_CHOOSER_COPY: Partial<
  Record<FlowBuilderStep, { title: string; description: string }>
> = {
  input: {
    title: 'Where will your input data come from?',
    description:
      'Choose the option that best describes the source of the text you will feed into this flow.',
  },
  output: {
    title: 'Where would you like to save your output?',
    description:
      'Choose the option that describes the destination to which you would like to persist the results of the flow.',
  },
}

export type CompletedSteps = ReadonlySet<FlowBuilderStep>

export function canNavigateToStep(step: FlowBuilderStep, completedSteps: CompletedSteps): boolean {
  if (step === 'input') return true
  if (step === 'output') return completedSteps.has('input')
  if (step === 'scaffold') return completedSteps.has('output')
  return false
}

export type BookendNodeLike = {
  type?: string
  data?: Record<string, unknown>
}

/** Whether the user may Continue past a bookend configure gate. */
export function canContinueBookendNode(node: BookendNodeLike): boolean {
  if (node.type === 'S3Input' || node.type === 'S3Output') {
    const bucket = node.data?.bucket
    return typeof bucket === 'string' && isValidS3BucketName(bucket)
  }
  if (node.type === 'JSONInput') {
    return isValidJsonInputData(node.data)
  }
  return true
}

/** Middle scaffold nodes may Continue once added (field validation is panel-level). */
export function canContinueMiddleNode(node: BookendNodeLike): boolean {
  return canContinueBookendNode(node)
}

export function bookendContinueHint(node: BookendNodeLike): string | null {
  if ((node.type === 'S3Input' || node.type === 'S3Output') && !canContinueBookendNode(node)) {
    const bucket = typeof node.data?.bucket === 'string' ? node.data.bucket : ''
    return s3BucketFieldError(bucket) ?? 'Enter the S3 bucket name before continuing.'
  }
  if (node.type === 'JSONInput' && !canContinueBookendNode(node)) {
    if (isJsonInputInvalidNodeData(node.data)) {
      return 'Fix the JSON syntax before continuing.'
    }
    return 'Add valid JSON with a "text" field before continuing.'
  }
  return null
}

/** Edit mode opens on the scaffold step with bookends already complete. */
export function getInitialEditStep(): FlowBuilderStep {
  return 'scaffold'
}

export function completedStepsForEdit(): Set<FlowBuilderStep> {
  return new Set(['input', 'output'])
}

export function isWizardBookendStep(step: FlowBuilderStep): boolean {
  return step === 'input' || step === 'output'
}

/** Continue/Cancel gate on wizard source/destination steps; configure gate elsewhere. */
export function isPanelGateActive(options: {
  readOnly: boolean
  configureGateActive: boolean
  activeStep: FlowBuilderStep
  isBookendSelected: boolean
}): boolean {
  if (options.readOnly) return false
  if (options.configureGateActive) return true
  return isWizardBookendStep(options.activeStep) && options.isBookendSelected
}

/** Persist-to-server save is only available on the scaffold step once both bookends exist. */
export function canSavePanelChanges(options: {
  activeStep: FlowBuilderStep
  inputNode: unknown
  outputNode: unknown
  hasChanges: boolean
}): boolean {
  if (!options.hasChanges) return false
  if (isWizardBookendStep(options.activeStep)) return false
  return Boolean(options.inputNode && options.outputNode)
}
