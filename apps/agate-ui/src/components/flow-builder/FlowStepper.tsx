import { Check } from 'lucide-react'
import { cn } from '@/lib/utils'
import {
  FLOW_BUILDER_STEPS,
  STEP_HEADINGS,
  type CompletedSteps,
  type FlowBuilderStep,
} from '@/lib/flowBuilderSteps'

type FlowStepperProps = {
  activeStep: FlowBuilderStep
  completedSteps: CompletedSteps
  onStepChange: (step: FlowBuilderStep) => void
  canNavigateTo: (step: FlowBuilderStep) => boolean
}

export default function FlowStepper({
  activeStep,
  completedSteps,
  onStepChange,
  canNavigateTo,
}: FlowStepperProps) {
  return (
    <nav aria-label="Flow setup steps" className="border-b bg-muted/30">
      <ol className="container mx-auto flex max-w-3xl items-center justify-between gap-2 px-4 py-4">
        {FLOW_BUILDER_STEPS.map((step, index) => {
          const isActive = activeStep === step
          const isComplete = completedSteps.has(step)
          const isLocked = !canNavigateTo(step)
          const stepNumber = index + 1

          return (
            <li key={step} className="flex flex-1 items-center gap-2">
              <button
                type="button"
                disabled={isLocked}
                onClick={() => onStepChange(step)}
                className={cn(
                  'flex min-w-0 flex-1 items-center gap-3 rounded-lg px-3 py-2 text-left transition-colors',
                  isActive && 'bg-background shadow-sm ring-1 ring-border',
                  !isActive && !isLocked && 'hover:bg-background/60',
                  isLocked && 'cursor-not-allowed opacity-50',
                )}
              >
                <span
                  className={cn(
                    'flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-medium',
                    isComplete && 'bg-primary text-primary-foreground',
                    isActive && !isComplete && 'bg-primary/10 text-primary ring-2 ring-primary',
                    !isActive && !isComplete && 'bg-muted text-muted-foreground',
                  )}
                >
                  {isComplete ? <Check className="h-4 w-4" aria-hidden /> : stepNumber}
                </span>
                <span className="min-w-0">
                  <span className="block text-sm font-medium leading-tight">{STEP_HEADINGS[step]}</span>
                  {isLocked && !isComplete && (
                    <span className="block text-xs text-muted-foreground">Complete the previous step first</span>
                  )}
                </span>
              </button>
              {index < FLOW_BUILDER_STEPS.length - 1 && (
                <div
                  className={cn(
                    'hidden h-px flex-1 bg-border sm:block',
                    completedSteps.has(step) && 'bg-primary/40',
                  )}
                  aria-hidden
                />
              )}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
