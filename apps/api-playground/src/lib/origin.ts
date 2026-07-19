const organizationSlugPattern = /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/

export const LOCAL_API_ORIGIN = "http://localhost:8004"
export const LOCAL_STYLEBOOK_API_ORIGIN = "http://localhost:8003"
export const LOCAL_AGATE_ORIGIN = "http://localhost:5173"
export const LOCAL_STYLEBOOK_ORIGIN = "http://localhost:5175"

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

export function deriveApiOrigin(organizationSlug: string): string {
  const slug = normalizeOrganizationSlug(organizationSlug)
  const error = validateOrganizationSlug(slug)
  if (error) {
    throw new Error(error)
  }
  return `https://api.${slug}.backfield.news`
}

export function deriveStylebookApiOrigin(organizationSlug: string): string {
  const slug = normalizeOrganizationSlug(organizationSlug)
  const error = validateOrganizationSlug(slug)
  if (error) {
    throw new Error(error)
  }
  return `https://stylebook.${slug}.backfield.news/api/stylebook`
}

export function deriveProductOrigin(
  product: "agate" | "stylebook",
  organizationSlug: string,
): string {
  const slug = normalizeOrganizationSlug(organizationSlug)
  const error = validateOrganizationSlug(slug)
  if (error) {
    throw new Error(error)
  }
  return `https://${product}.${slug}.backfield.news`
}

export function organizationSlugFromPlaygroundHost(hostname: string): string {
  const labels = hostname.toLowerCase().replace(/\.$/, "").split(".")
  if (
    labels.length !== 4 ||
    labels[0] !== "playground" ||
    labels[2] !== "backfield" ||
    labels[3] !== "news"
  ) {
    return ""
  }
  const slug = normalizeOrganizationSlug(labels[1])
  return validateOrganizationSlug(slug) ? "" : slug
}

export function isLocalPlaygroundHost(hostname: string): boolean {
  return hostname === "localhost" || hostname === "127.0.0.1"
}
