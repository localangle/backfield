import { Label } from '@/components/ui/label'
import type { ReactNode } from 'react'

type FieldLabelProps = {
  htmlFor: string
  required?: boolean
  className?: string
  children: ReactNode
}

/** Panel field label with optional required asterisk; uses default Label typography. */
export function FieldLabel({ htmlFor, required, className, children }: FieldLabelProps) {
  return (
    <Label htmlFor={htmlFor} className={className}>
      {children}
      {required ? (
        <>
          <span className="sr-only"> (required)</span>
          <span className="ml-0.5 text-destructive" aria-hidden>
            *
          </span>
        </>
      ) : null}
    </Label>
  )
}
