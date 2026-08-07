export interface SessionOrganization {
  id: number
  name: string
  slug: string
}

export interface SessionUser {
  authenticated: boolean
  email: string
  organizationId: number
  organizationName: string
  organizationSlug: string
  orgRole: string | null
  organizations: SessionOrganization[]
}

export interface PlatformProject {
  id: number
  name: string
  slug: string
}

export interface PlatformWorkspace {
  id: number
  name: string
  slug: string
  projects: PlatformProject[]
}

export interface PlatformStylebook {
  id: number
  name: string
  slug: string
  is_default: boolean
}

export interface PlatformContext {
  user: SessionUser
  workspaces: PlatformWorkspace[]
  stylebooks: PlatformStylebook[]
}

interface MeOrganization {
  id?: number
  name?: string
  slug?: string
}

interface MeResponse {
  authenticated?: boolean
  email?: string
  organization_id?: number
  organization_name?: string | null
  organization_slug?: string | null
  org_role?: string | null
  organizations?: MeOrganization[]
}

/** Thrown when the browser has no usable Backfield session; callers redirect to Agate login. */
export class SessionAuthRequiredError extends Error {
  constructor() {
    super("Sign in to Backfield before opening the API Playground.")
    this.name = "SessionAuthRequiredError"
  }
}

async function sessionJson<T>(origin: string, path: string): Promise<T> {
  const response = await fetch(`${origin}${path}`, {
    credentials: "include",
    headers: { Accept: "application/json" },
    referrerPolicy: "no-referrer",
  })
  if (!response.ok) {
    if (response.status === 401 || response.status === 403) {
      throw new SessionAuthRequiredError()
    }
    throw new Error(`Backfield session request failed with ${response.status}.`)
  }
  return (await response.json()) as T
}

export async function logoutSession(coreOrigin: string): Promise<void> {
  try {
    await fetch(`${coreOrigin}/v1/auth/logout`, {
      method: "POST",
      credentials: "include",
      referrerPolicy: "no-referrer",
    })
  } catch {
    // Match the other apps: leave the signed-in shell even if logout cannot be confirmed.
  }
}

export async function switchOrganization(
  coreOrigin: string,
  organizationId: number,
): Promise<void> {
  const response = await fetch(`${coreOrigin}/v1/auth/switch-organization`, {
    method: "POST",
    credentials: "include",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    referrerPolicy: "no-referrer",
    body: JSON.stringify({ organization_id: organizationId }),
  })
  if (!response.ok) {
    if (response.status === 401 || response.status === 403) {
      throw new SessionAuthRequiredError()
    }
    throw new Error("Could not switch organizations.")
  }
}

function parseOrganizations(raw: MeOrganization[] | undefined): SessionOrganization[] {
  if (!Array.isArray(raw)) return []
  return raw
    .map((item) => {
      if (item.id == null || !item.name?.trim() || !item.slug?.trim()) return null
      return {
        id: item.id,
        name: item.name.trim(),
        slug: item.slug.trim().toLowerCase(),
      }
    })
    .filter((item): item is SessionOrganization => item != null)
}

export async function fetchPlatformContext(
  coreOrigin: string,
  stylebookApiOrigin: string,
): Promise<PlatformContext> {
  const me = await sessionJson<MeResponse>(coreOrigin, "/v1/auth/me")
  if (!me.authenticated || !me.email || me.organization_id == null) {
    throw new SessionAuthRequiredError()
  }

  const [workspaces, stylebooks] = await Promise.all([
    sessionJson<PlatformWorkspace[]>(coreOrigin, "/v1/me/workspaces"),
    sessionJson<PlatformStylebook[]>(
      stylebookApiOrigin,
      `/v1/organizations/${me.organization_id}/stylebooks`,
    ),
  ])

  return {
    user: {
      authenticated: true,
      email: me.email,
      organizationId: me.organization_id,
      organizationName: me.organization_name?.trim() || "Backfield",
      organizationSlug: me.organization_slug?.trim().toLowerCase() || "",
      orgRole: me.org_role ?? null,
      organizations: parseOrganizations(me.organizations),
    },
    workspaces,
    stylebooks,
  }
}
