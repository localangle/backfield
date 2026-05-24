import { AGATE_PRODUCT_MARK } from './agateBrand'
import { cn } from './cn'

/** Matches Stylebook header mark (``size-7`` / 28px box). */
const DEFAULT_MARK_CLASS = 'size-7 text-[1.75rem] font-semibold leading-none'

/**
 * Agate ⊞ mark in a fixed box so it optically matches Lucide product marks (e.g. Stylebook).
 * Pass ``size-4`` / ``size-5`` in sidebars; glyph uses a slightly larger ``text-*`` than the box.
 */
export function AgateProductMark({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        'inline-flex shrink-0 items-center justify-center font-semibold leading-none',
        DEFAULT_MARK_CLASS,
        className,
      )}
      aria-hidden
    >
      {AGATE_PRODUCT_MARK}
    </span>
  )
}
