import { LayoutTemplate } from 'lucide-react'

import { cn } from './cn'

/** Matches Stylebook header mark (``size-7`` / 28px box). */
const DEFAULT_MARK_CLASS = 'size-7 stroke-[1.75]'

export function AgateProductMark({ className }: { className?: string }) {
  return <LayoutTemplate className={cn('shrink-0', DEFAULT_MARK_CLASS, className)} aria-hidden />
}
