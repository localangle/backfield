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
    <nav aria-label="Flow setup steps" className="border-b">
      <ol className="container mx-auto flex max-w-3xl items-center gap-1 px-4 py-2.5">
        {FLOW_BUILDER_STEPS.map((step, index) => {
          const isActive = activeStep === step
          const isComplete = completedSteps.has(step)
          const isLocked = !canNavigateTo(step)
          const stepNumber = index + 1

          return (
            <li key={step} className="flex min-w-0 flex-1 items-center gap-1">
              <button
                type="button"
                disabled={isLocked}
                onClick={() => onStepChange(step)}
                aria-current={isActive ? 'step' : undefined}
                className={cn(
                  'flex min-w-0 flex-1 items-center gap-2 rounded-md px-2 py-1 text-left transition-colors',
                  isActive && 'text-foreground',
                  !isActive && !isLocked && 'text-muted-foreground hover:text-foreground',
                  isLocked && 'cursor-not-allowed text-muted-foreground/50',
                )}
              >
                <span
                  className={cn(
                    'flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[11px] font-medium',
                    isComplete && 'bg-primary/15 text-primary',
                    isActive && !isComplete && 'bg-foreground text-background',
                    !isActive && !isComplete && 'bg-muted text-muted-foreground',
                  )}
                >
                  {isComplete ? <Check className="h-3 w-3" aria-hidden /> : stepNumber}
                </span>
                <span
                  className={cn(
                    'truncate text-xs leading-tight',
                    isActive ? 'font-medium' : 'font-normal',
                  )}
                >
                  {STEP_HEADINGS[step]}
                </span>
              </button>
              {index < FLOW_BUILDER_STEPS.length - 1 && (
                <div
                  className={cn(
                    'hidden h-px w-4 shrink-0 bg-border sm:block',
                    completedSteps.has(step) && 'bg-primary/25',
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
