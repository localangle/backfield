/** Core API (session cookie) — same-origin via Vite `/v1` proxy. */

const coreBase = () => import.meta.env.VITE_AUTH_API_BASE ?? ""

async function jsonFetch<T>(path: string, init?: RequestInit): Promise<T> {
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
  organization_name?: string | null
  org_role?: string | null
}

export async function fetchMe(): Promise<MeResponse> {
  return jsonFetch<MeResponse>("/v1/auth/me")
}

export interface ProjectSummary {
  id: number
  name: string
  slug: string
}

/** Workspaces and visible projects for the signed-in user (session only). */
export async function listMyWorkspaces(): Promise<WorkspaceWithProjects[]> {
  return jsonFetch<WorkspaceWithProjects[]>("/v1/me/workspaces")
}

export interface WorkspaceWithProjects {
  id: number
  name: string
  slug: string
  projects: ProjectSummary[]
  stylebook_id?: number | null
  stylebook_name?: string | null
}
