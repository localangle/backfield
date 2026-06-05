/** Article headline / URL display helpers for canonical mention rows. */

export interface MentionArticleFields {
  article_id: number
  article_headline?: string | null
  article_url?: string | null
}

export function mentionArticleDisplayTitle(m: MentionArticleFields): string {
  const trimmed = (m.article_headline ?? "").trim()
  if (trimmed.length > 0) return trimmed
  return `Article ${m.article_id}`
}

export function mentionArticleHref(m: MentionArticleFields): string | null {
  const u = (m.article_url ?? "").trim()
  return u.length > 0 ? u : null
}

/** Location mention nature pill styling (Stylebook location canonical detail). */

export function mentionNatureDisplayLabel(raw: string | null | undefined): string {
  const s = (raw ?? "").trim().toLowerCase()
  if (!s) return "Unknown"
  return s.charAt(0).toUpperCase() + s.slice(1)
}

export function mentionNatureBadgeClass(raw: string | null | undefined): string {
  const s = (raw ?? "").trim().toLowerCase()
  switch (s) {
    case "primary":
      return "border-primary/35 bg-primary/10 text-primary"
    case "secondary":
      return "border-muted-foreground/25 bg-muted text-muted-foreground"
    case "subject":
      return "border-violet-500/40 bg-violet-500/10 text-violet-900 dark:text-violet-200"
    case "context":
      return "border-sky-500/40 bg-sky-500/10 text-sky-900 dark:text-sky-100"
    case "person":
      return "border-amber-500/45 bg-amber-500/12 text-amber-950 dark:text-amber-100"
    default:
      return "border-border bg-background text-muted-foreground"
  }
}
