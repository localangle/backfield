/**
 * PlaceExtract / mention nature pill styling (aligned with Stylebook location detail).
 */

export function mentionNatureDisplayLabel(raw: string | null | undefined): string {
  const s = (raw ?? '').trim().toLowerCase()
  if (!s) return 'Unknown'
  return s.charAt(0).toUpperCase() + s.slice(1)
}

export function mentionNatureBadgeClass(raw: string | null | undefined): string {
  const s = (raw ?? '').trim().toLowerCase()
  switch (s) {
    case 'primary':
      return 'border-primary/35 bg-primary/10 text-primary'
    case 'secondary':
      return 'border-muted-foreground/25 bg-muted text-muted-foreground'
    case 'subject':
      return 'border-violet-500/40 bg-violet-500/10 text-violet-900 dark:text-violet-200'
    case 'context':
      return 'border-sky-500/40 bg-sky-500/10 text-sky-900 dark:text-sky-100'
    case 'person':
      return 'border-amber-500/45 bg-amber-500/12 text-amber-950 dark:text-amber-100'
    default:
      return 'border-border bg-background text-muted-foreground'
  }
}
