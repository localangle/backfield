/** Core API (session cookie) helpers — same origin as Agate UI via Vite proxy. */

const coreBase = () => import.meta.env.VITE_AUTH_API_BASE ?? ''

async function jsonFetch<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const r = await fetch(`${coreBase()}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  })
  if (!r.ok) {
    let detail = r.statusText
    try {
      const body = (await r.json()) as { detail?: string | unknown }
      if (typeof body.detail === "string") {
        detail = body.detail
      }
    } catch {
      /* ignore */
    }
    throw new Error(detail)
  }
  if (r.status === 204) {
    return undefined as T
  }
  return (await r.json()) as T
}

export interface MeResponse {
  authenticated?: boolean
  email?: string
  user_id?: number
  organization_id?: number
  org_role?: string | null
}

export async function fetchMe(): Promise<MeResponse> {
  return jsonFetch<MeResponse>("/v1/auth/me")
}

export async function changePassword(
  currentPassword: string,
  newPassword: string,
): Promise<void> {
  await jsonFetch("/v1/auth/change-password", {
    method: "POST",
    body: JSON.stringify({
      current_password: currentPassword,
      new_password: newPassword,
    }),
  })
}

export interface ProjectSummary {
  id: number
  name: string
  slug: string
}

export async function listOrgProjects(orgId: number): Promise<ProjectSummary[]> {
  return jsonFetch(`/v1/organizations/${orgId}/projects`)
}

export interface ProjectMembershipRow {
  project_id: number
  slug: string
  name: string
  role: string | null
}

export interface OrgUserRow {
  id: number
  email: string
  display_name: string | null
  role: string
  disabled_at: string | null
  project_memberships: ProjectMembershipRow[] | null
}

export async function listOrgUsers(
  orgId: number,
  detail: boolean,
): Promise<OrgUserRow[]> {
  const q = detail ? "?detail=true" : ""
  return jsonFetch(`/v1/organizations/${orgId}/users${q}`)
}

export async function createOrgUser(
  orgId: number,
  body: {
    email: string
    password: string
    display_name?: string | null
    role: string
  },
): Promise<OrgUserRow> {
  return jsonFetch(`/v1/organizations/${orgId}/users`, {
    method: "POST",
    body: JSON.stringify(body),
  })
}

export async function patchOrgUser(
  orgId: number,
  userId: number,
  body: { display_name?: string | null; role?: string | null },
): Promise<OrgUserRow> {
  return jsonFetch(`/v1/organizations/${orgId}/users/${userId}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  })
}

export async function disableOrgUser(
  orgId: number,
  userId: number,
): Promise<void> {
  await jsonFetch(`/v1/organizations/${orgId}/users/${userId}`, {
    method: "DELETE",
  })
}

export async function replaceProjectMemberships(
  orgId: number,
  userId: number,
  memberships: { project_id: number; role: string | null }[],
): Promise<ProjectMembershipRow[]> {
  return jsonFetch(
    `/v1/organizations/${orgId}/users/${userId}/project-memberships`,
    {
      method: "PUT",
      body: JSON.stringify({ memberships }),
    },
  )
}
