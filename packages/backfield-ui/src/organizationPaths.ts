export interface OrganizationPathScope {
  scopedPathname: string
  requestedOrganizationSlug: string | null
  redirectPath: string | null
}

export function scopeOrganizationPath(
  pathname: string,
  search: string,
  activeOrganizationSlug: string,
): OrganizationPathScope {
  const match = pathname.match(/^\/org\/([^/]+)(\/.*)?$/)
  const requestedOrganizationSlug = match?.[1]
    ? decodeURIComponent(match[1])
    : null
  const scopedPathname = match ? match[2] || "/" : pathname
  if (!match || requestedOrganizationSlug !== activeOrganizationSlug) {
    return {
      scopedPathname,
      requestedOrganizationSlug,
      redirectPath: `/org/${encodeURIComponent(activeOrganizationSlug)}${scopedPathname}${search}`,
    }
  }
  return { scopedPathname, requestedOrganizationSlug, redirectPath: null }
}
