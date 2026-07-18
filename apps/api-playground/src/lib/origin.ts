const organizationSlugPattern = /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/

export const LOCAL_API_ORIGIN = "http://localhost:8004"

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

export function isLocalPlaygroundHost(hostname: string): boolean {
  return hostname === "localhost" || hostname === "127.0.0.1"
}
