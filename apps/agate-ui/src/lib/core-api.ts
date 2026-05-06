/** Core API (session cookie) helpers — same origin as Agate UI via Vite proxy. */

const coreBase = () => import.meta.env.VITE_AUTH_API_BASE ?? ''

function formatCoreApiErrorBody(body: unknown): string {
  if (!body || typeof body !== "object") return "Request failed"
  const detail = (body as { detail?: unknown }).detail
  if (typeof detail === "string") return detail
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (item && typeof item === "object" && "msg" in item) {
          return String((item as { msg?: unknown }).msg ?? JSON.stringify(item))
        }
        return typeof item === "string" ? item : JSON.stringify(item)
      })
      .join(" ")
  }
  if (detail != null && typeof detail === "object") return JSON.stringify(detail)
  return "Request failed"
}

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
      const body = await r.json()
      detail = formatCoreApiErrorBody(body)
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
  /** Display name of the organization (publication / tenant). */
  organization_name?: string | null
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

export interface AiModelConfigSummary {
  id: string
  name: string
  provider: string
  provider_model_id: string
  litellm_model?: string | null
  integration_secret_id?: number | null
  model_kind: string
  status: string
  capabilities: string[]
  latest_test_status?: string | null
}

/** Full org catalog row from Core API (admin list/create/patch/test). */
export interface AiModelConfigRow extends AiModelConfigSummary {
  organization_id: number
  config_json?: Record<string, unknown> | null
  input_token_price?: string | number | null
  output_token_price?: string | number | null
  currency: string
  latest_tested_at?: string | null
  latest_test_error?: string | null
}

export async function listOrganizationAiModels(
  orgId: number,
): Promise<AiModelConfigRow[]> {
  return jsonFetch(`/v1/organizations/${orgId}/ai-models`)
}

export interface CuratedAiModelOption {
  curated_id: string
  provider: string
  provider_model_id: string
  label: string
  capabilities: string[]
  input_token_price?: string | number | null
  output_token_price?: string | number | null
  currency?: string | null
}

export async function listAiModelCuratedOptions(
  orgId: number,
): Promise<CuratedAiModelOption[]> {
  return jsonFetch(`/v1/organizations/${orgId}/ai-models/curated-options`)
}

export interface AiModelConfigCreateInput {
  name?: string | null
  curated_id?: string | null
  provider?: string | null
  provider_model_id?: string | null
  litellm_model?: string | null
  integration_secret_id?: number | null
  model_kind?: string
  capabilities?: string[] | null
  config_json?: Record<string, unknown> | null
  input_token_price?: number | null
  output_token_price?: number | null
  currency?: string
}

export async function createOrganizationAiModel(
  orgId: number,
  body: AiModelConfigCreateInput,
): Promise<AiModelConfigRow> {
  return jsonFetch(`/v1/organizations/${orgId}/ai-models`, {
    method: "POST",
    body: JSON.stringify(body),
  })
}

export interface AiModelConfigPatchInput {
  name?: string
  status?: string
  capabilities?: string[]
  currency?: string
  input_token_price?: number | null
  output_token_price?: number | null
  model_kind?: string
  config_json?: Record<string, unknown> | null
  litellm_model?: string
  integration_secret_id?: number
}

export async function patchOrganizationAiModel(
  orgId: number,
  configId: string,
  body: AiModelConfigPatchInput,
): Promise<AiModelConfigRow> {
  return jsonFetch(`/v1/organizations/${orgId}/ai-models/${encodeURIComponent(configId)}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  })
}

export async function deleteOrganizationAiModel(orgId: number, configId: string): Promise<void> {
  await jsonFetch(`/v1/organizations/${orgId}/ai-models/${encodeURIComponent(configId)}`, {
    method: "DELETE",
  })
}

export async function testOrganizationAiModelConnection(
  orgId: number,
  configId: string,
): Promise<AiModelConfigRow> {
  return jsonFetch(
    `/v1/organizations/${orgId}/ai-models/${encodeURIComponent(configId)}/test-connection`,
    { method: "POST" },
  )
}

/** Saved vendor credentials and catalog linkage metadata (no secret values). */
export interface AiCredentialLinkedCatalogModel {
  id: string
  name: string
}

export interface AiCredentialCatalogEntry {
  integration_secret_id: number | null
  integration_key: string
  credential_kind: 'preset' | 'custom'
  provider: string | null
  configured: boolean
  display_name?: string | null
  has_api_base: boolean
  linked_catalog_models: AiCredentialLinkedCatalogModel[]
  created_at: string | null
  updated_at: string | null
}

export async function listAiCredentialsCatalog(orgId: number): Promise<AiCredentialCatalogEntry[]> {
  return jsonFetch(`/v1/organizations/${orgId}/integration-secrets/catalog`)
}

export interface IntegrationSecretMetadata {
  integration_secret_id?: number | null
  integration_key: string
  created_at: string
  updated_at: string
}

export async function putOrganizationIntegrationSecret(
  orgId: number,
  integrationKey: string,
  payload: { value: string; display_name?: string | null; api_base?: string | null },
): Promise<IntegrationSecretMetadata> {
  const enc = encodeURIComponent(integrationKey)
  const body: { value: string; display_name?: string | null; api_base?: string | null } = {
    value: payload.value,
  }
  if (payload.display_name !== undefined) {
    body.display_name = payload.display_name === '' ? null : payload.display_name
  }
  if (payload.api_base !== undefined) {
    body.api_base = payload.api_base === '' ? null : payload.api_base
  }
  return jsonFetch(`/v1/organizations/${orgId}/integration-secrets/${enc}`, {
    method: "PUT",
    body: JSON.stringify(body),
  })
}

export interface IntegrationSecretCreateInput {
  value: string
  display_name?: string | null
  api_base?: string | null
}

export interface IntegrationSecretCreatedResponse {
  integration_secret_id: number
  integration_key: string
  created_at: string
  updated_at: string
}

export async function createOrganizationAiCredential(
  orgId: number,
  body: IntegrationSecretCreateInput,
): Promise<IntegrationSecretCreatedResponse> {
  return jsonFetch(`/v1/organizations/${orgId}/integration-secrets`, {
    method: "POST",
    body: JSON.stringify(body),
  })
}

export interface IntegrationSecretPatchInput {
  value?: string
  display_name?: string | null
  api_base?: string | null
}

export async function patchOrganizationIntegrationSecret(
  orgId: number,
  integrationKey: string,
  body: IntegrationSecretPatchInput,
): Promise<IntegrationSecretMetadata> {
  const enc = encodeURIComponent(integrationKey)
  return jsonFetch(`/v1/organizations/${orgId}/integration-secrets/${enc}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  })
}

export async function deleteOrganizationIntegrationSecret(
  orgId: number,
  integrationKey: string,
): Promise<void> {
  const enc = encodeURIComponent(integrationKey)
  await jsonFetch(`/v1/organizations/${orgId}/integration-secrets/${enc}`, {
    method: "DELETE",
  })
}

export interface ProjectEffectiveAiModelRow extends AiModelConfigSummary {
  project_enabled: boolean
}

export async function fetchProjectEffectiveAiModels(
  projectId: number,
  capabilities?: string[],
): Promise<ProjectEffectiveAiModelRow[]> {
  const q = capabilities?.length
    ? `?capabilities=${encodeURIComponent(capabilities.join(','))}`
    : ''
  return jsonFetch(`/v1/projects/${projectId}/ai-models/effective${q}`)
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

export async function createWorkspace(
  orgId: number,
  body: { name: string; stylebook_id?: number | null },
): Promise<WorkspaceWithProjects> {
  return jsonFetch(`/v1/organizations/${orgId}/workspaces`, {
    method: "POST",
    body: JSON.stringify(body),
  })
}

export interface OrganizationSummary {
  id: number
  name: string
  slug: string
}

export async function patchOrganization(
  orgId: number,
  body: { name: string },
): Promise<OrganizationSummary> {
  return jsonFetch(`/v1/organizations/${orgId}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  })
}

export async function patchWorkspace(
  orgId: number,
  workspaceId: number,
  body: { name?: string; stylebook_id?: number },
): Promise<WorkspaceWithProjects> {
  return jsonFetch(`/v1/organizations/${orgId}/workspaces/${workspaceId}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  })
}

export interface OrgStylebook {
  id: number
  name: string
  slug: string
  is_default: boolean
}

export async function listOrgStylebooks(orgId: number): Promise<OrgStylebook[]> {
  return jsonFetch(`/v1/organizations/${orgId}/stylebooks`)
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
  stylebook_id?: number | null
  stylebook_name?: string | null
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
