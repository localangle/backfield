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

export async function listOrgWorkspaces(
  orgId: number,
): Promise<WorkspaceWithProjects[]> {
  return jsonFetch(`/v1/organizations/${orgId}/workspaces`)
}

/** Workspaces and visible projects for the signed-in user (session only). */
export async function listMyWorkspaces(): Promise<WorkspaceWithProjects[]> {
  return jsonFetch(`/v1/me/workspaces`)
}

export interface ProjectMembershipRow {
  project_id: number
  slug: string
  name: string
  role: string | null
}

export interface WorkspaceMembershipRow {
  id: number
  name: string
  slug: string
}

export interface OrgUserRow {
  id: number
  email: string
  display_name: string | null
  role: string
  disabled_at: string | null
  project_memberships: ProjectMembershipRow[] | null
  workspace_memberships: WorkspaceMembershipRow[] | null
}

export interface WorkspaceWithProjects {
  id: number
  name: string
  slug: string
  projects: ProjectSummary[]
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

/** @deprecated Prefer workspace-based access via replaceWorkspaceMemberships. */
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

export async function replaceWorkspaceMemberships(
  orgId: number,
  userId: number,
  workspaceIds: number[],
): Promise<WorkspaceMembershipRow[]> {
  return jsonFetch(
    `/v1/organizations/${orgId}/users/${userId}/workspace-memberships`,
    {
      method: "PUT",
      body: JSON.stringify({ workspace_ids: workspaceIds }),
    },
  )
}

/** Core API project Bearer keys (`bfk_…`) — distinct from Agate project secrets. */
export interface ProjectAccessCredential {
  id: number
  credential_type: string
  key_prefix: string
  label: string | null
  created_at: string
  revoked_at: string | null
  user_id: number | null
}

export interface ProjectAccessCredentialCreated extends ProjectAccessCredential {
  raw_key: string
}

export async function listProjectAccessKeys(
  projectId: number,
): Promise<ProjectAccessCredential[]> {
  return jsonFetch(`/v1/projects/${projectId}/api-keys`)
}

export async function createProjectAccessKey(
  projectId: number,
  body: { credential_type: "user" | "service"; label?: string | null },
): Promise<ProjectAccessCredentialCreated> {
  return jsonFetch(`/v1/projects/${projectId}/api-keys`, {
    method: "POST",
    body: JSON.stringify({
      credential_type: body.credential_type,
      label: body.label ?? null,
    }),
  })
}

export async function revokeProjectAccessKey(
  projectId: number,
  credentialId: number,
): Promise<void> {
  await jsonFetch(`/v1/projects/${projectId}/api-keys/${credentialId}`, {
    method: "DELETE",
  })
}
