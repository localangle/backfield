import { useEffect, useRef } from 'react'

export interface ProcessedItemArticleBodyProps {
  body: string
  /** When set, that UTF-16 range is visually emphasized. */
  highlight: { start: number; end: number } | null
  /**
   * Changes to this value (e.g. selected place id) scroll the highlight into view when
   * ``highlight`` is a valid range.
   */
  scrollWhenKey: string | null
}

/**
 * Renders article text with an optional single highlight range. Does not invent a highlight
 * when ``highlight`` is null.
 */
export function ProcessedItemArticleBody({ body, highlight, scrollWhenKey }: ProcessedItemArticleBodyProps) {
  const markRef = useRef<HTMLElement | null>(null)

  useEffect(() => {
    if (!highlight || scrollWhenKey === null || scrollWhenKey === '') {
      return
    }
    const el = markRef.current
    if (!el) return
    el.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'nearest' })
  }, [scrollWhenKey, highlight])

  if (!highlight) {
    return (
      <div className="whitespace-pre-wrap font-sans text-sm leading-relaxed text-foreground">{body}</div>
    )
  }

  const { start, end } = highlight
  if (start < 0 || end > body.length || end <= start) {
    return (
      <div className="whitespace-pre-wrap font-sans text-sm leading-relaxed text-foreground">{body}</div>
    )
  }

  const before = body.slice(0, start)
  const mid = body.slice(start, end)
  const after = body.slice(end)

  return (
    <div className="whitespace-pre-wrap font-sans text-sm leading-relaxed text-foreground">
      {before}
      <mark
        ref={markRef}
        className="rounded-sm bg-amber-200/90 px-0.5 text-foreground dark:bg-amber-500/40"
      >
        {mid}
      </mark>
      {after}
    </div>
  )
}
