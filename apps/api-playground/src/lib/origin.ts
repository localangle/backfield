const organizationSlugPattern = /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/

export const LOCAL_API_ORIGIN = "http://localhost:8004"
export const LOCAL_STYLEBOOK_API_ORIGIN = "http://localhost:8003"
export const LOCAL_AGATE_ORIGIN = "http://localhost:5173"
export const LOCAL_STYLEBOOK_ORIGIN = "http://localhost:5175"

/** Parent domain after `{app}.{slug}.` — production or staging. */
export type ParentDomain = "backfield.news" | "stg.backfield.news"

export type PlaygroundTenant = {
  slug: string
  parentDomain: ParentDomain
}

export function normalizeOrganizationSlug(value: string): string {
  return value.trim().toLowerCase()
}

export function validateOrganizationSlug(value: string): string | undefined {
  const slug = normalizeOrganizationSlug(value)
  if (!slug) {
    return "Enter your organization slug."
  }
  if (!organizationSlugPattern.test(slug)) {
    return "Use 1–63 lowercase letters, numbers, or hyphens; start and end with a letter or number."
  }
  return undefined
}

function requireSlug(organizationSlug: string): string {
  const slug = normalizeOrganizationSlug(organizationSlug)
  const error = validateOrganizationSlug(slug)
  if (error) {
    throw new Error(error)
  }
  return slug
}

export function deriveApiOrigin(
  organizationSlug: string,
  parentDomain: ParentDomain = "backfield.news",
): string {
  return `https://api.${requireSlug(organizationSlug)}.${parentDomain}`
}

export function deriveStylebookApiOrigin(
  organizationSlug: string,
  parentDomain: ParentDomain = "backfield.news",
): string {
  return `https://stylebook.${requireSlug(organizationSlug)}.${parentDomain}/api/stylebook`
}

export function deriveProductOrigin(
  product: "agate" | "stylebook",
  organizationSlug: string,
  parentDomain: ParentDomain = "backfield.news",
): string {
  return `https://${product}.${requireSlug(organizationSlug)}.${parentDomain}`
}

/**
 * Parse a tenant Playground hostname.
 *
 * Production: `playground.{slug}.backfield.news`
 * Staging:    `playground.{slug}.stg.backfield.news`
 */
export function parsePlaygroundHost(hostname: string): PlaygroundTenant | null {
  const labels = hostname.toLowerCase().replace(/\.$/, "").split(".")
  let slug = ""
  let parentDomain: ParentDomain | null = null

  if (
    labels.length === 4 &&
    labels[0] === "playground" &&
    labels[2] === "backfield" &&
    labels[3] === "news"
  ) {
    slug = normalizeOrganizationSlug(labels[1] ?? "")
    parentDomain = "backfield.news"
  } else if (
    labels.length === 5 &&
    labels[0] === "playground" &&
    labels[2] === "stg" &&
    labels[3] === "backfield" &&
    labels[4] === "news"
  ) {
    slug = normalizeOrganizationSlug(labels[1] ?? "")
    parentDomain = "stg.backfield.news"
  }

  if (!parentDomain || validateOrganizationSlug(slug)) {
    return null
  }
  return { slug, parentDomain }
}

export function organizationSlugFromPlaygroundHost(hostname: string): string {
  return parsePlaygroundHost(hostname)?.slug ?? ""
}

export function isLocalPlaygroundHost(hostname: string): boolean {
  return hostname === "localhost" || hostname === "127.0.0.1"
}
