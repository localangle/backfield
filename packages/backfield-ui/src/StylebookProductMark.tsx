import { BookOpen } from 'lucide-react'

import { cn } from './cn'

/** Matches Agate header mark size (``text-[1.75rem]`` / 28px). */
const DEFAULT_MARK_CLASS = 'size-7 stroke-[1.75]'

export function StylebookProductMark({ className }: { className?: string }) {
  return <BookOpen className={cn('shrink-0', DEFAULT_MARK_CLASS, className)} aria-hidden />
}
