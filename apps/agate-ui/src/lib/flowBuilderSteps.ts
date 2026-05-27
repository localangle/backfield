import { isValidJsonInputData } from '@/lib/jsonInputValidation'

export type FlowBuilderStep = 'input' | 'output' | 'scaffold'

export const FLOW_BUILDER_STEPS: FlowBuilderStep[] = ['input', 'output', 'scaffold']

export const STEP_HEADINGS: Record<FlowBuilderStep, string> = {
  input: 'Choose a source',
  output: 'Choose a destination',
  scaffold: 'Build your flow',
}

export const STEP_DESCRIPTIONS: Record<FlowBuilderStep, string> = {
  input: 'Choose how articles or content enter this flow.',
  output: 'Choose where this flow saves its results.',
  scaffold: 'Add steps between your source and destination.',
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
  if (node.type === 'S3Input') {
    const bucket = node.data?.bucket
    return typeof bucket === 'string' && bucket.trim() !== ''
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
  if (node.type === 'S3Input' && !canContinueBookendNode(node)) {
    return 'Enter the S3 bucket name before continuing.'
  }
  if (node.type === 'JSONInput' && !canContinueBookendNode(node)) {
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
