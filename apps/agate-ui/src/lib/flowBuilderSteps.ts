export type FlowBuilderStep = 'input' | 'output' | 'scaffold'

export const FLOW_BUILDER_STEPS: FlowBuilderStep[] = ['input', 'output', 'scaffold']

export const STEP_HEADINGS: Record<FlowBuilderStep, string> = {
  input: 'Choose an input',
  output: 'Choose an output',
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
    title: 'First, choose an input',
    description:
      'Pick how articles or content enter this flow — paste text, provide structured JSON, or read files from cloud storage.',
  },
  output: {
    title: 'Second, choose an output',
    description:
      'Pick where this flow sends its results — as JSON for review and export, or to your organization Stylebook.',
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
    const text = node.data?.text
    return typeof text === 'string' && text.trim() !== ''
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
    return 'Add JSON with a non-empty text field before continuing.'
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
