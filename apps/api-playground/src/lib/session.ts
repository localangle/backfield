export interface SessionUser {
  authenticated: boolean
  email: string
  organizationId: number
  organizationName: string
  orgRole: string | null
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

interface MeResponse {
  authenticated?: boolean
  email?: string
  organization_id?: number
  organization_name?: string | null
  org_role?: string | null
}

async function sessionJson<T>(origin: string, path: string): Promise<T> {
  const response = await fetch(`${origin}${path}`, {
    credentials: "include",
    headers: { Accept: "application/json" },
    referrerPolicy: "no-referrer",
  })
  if (!response.ok) {
    throw new Error(
      response.status === 401 || response.status === 403
        ? "Sign in to Backfield before opening the API Playground."
        : `Backfield session request failed with ${response.status}.`,
    )
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

export async function fetchPlatformContext(
  coreOrigin: string,
  stylebookApiOrigin: string,
): Promise<PlatformContext> {
  const me = await sessionJson<MeResponse>(coreOrigin, "/v1/auth/me")
  if (!me.authenticated || !me.email || me.organization_id == null) {
    throw new Error("Sign in to Backfield before opening the API Playground.")
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
      orgRole: me.org_role ?? null,
    },
    workspaces,
    stylebooks,
  }
}
