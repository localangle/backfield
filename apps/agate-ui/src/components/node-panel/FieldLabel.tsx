import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'
import type { ReactNode } from 'react'

type FieldLabelProps = {
  htmlFor: string
  required?: boolean
  className?: string
  children: ReactNode
}

/** Compact panel field label; shows a red asterisk when `required` is true. */
export function FieldLabel({ htmlFor, required, className, children }: FieldLabelProps) {
  return (
    <Label htmlFor={htmlFor} className={cn('text-xs text-muted-foreground', className)}>
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
