/** Core API (session cookie) helpers — same origin as Agate UI via Vite proxy. */
import { handleTenantResponse } from "@backfield/ui/tenantSession"

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
  const r = await handleTenantResponse(await fetch(`${coreBase()}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  }))
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
  organization_slug?: string | null
  org_role?: string | null
  must_change_password?: boolean
  organizations?: { id: number; name: string; slug: string }[]
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
  model_kind?: string
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

/** Metadata for all organization integration secrets (org admin). */
export async function listOrganizationIntegrationSecretMetadata(
  orgId: number,
): Promise<IntegrationSecretMetadata[]> {
  return jsonFetch(`/v1/organizations/${orgId}/integration-secrets`)
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
  /** Present once Core API supports project keys (omit on older stacks). */
  project_credential_override_configured?: boolean
}

export async function fetchProjectEffectiveAiModels(
  projectId: number,
  capabilities?: string[],
  options?: { includeDisabled?: boolean },
): Promise<ProjectEffectiveAiModelRow[]> {
  const params = new URLSearchParams()
  if (capabilities?.length) {
    params.set('capabilities', capabilities.join(','))
  }
  if (options?.includeDisabled) {
    params.set('include_disabled', 'true')
  }
  const q = params.toString()
  const suffix = q ? `?${q}` : ''
  return jsonFetch(`/v1/projects/${projectId}/ai-models/effective${suffix}`)
}

export async function putProjectAiModelAvailability(
  projectId: number,
  modelConfigId: string,
  enabled: boolean,
): Promise<ProjectEffectiveAiModelRow> {
  return jsonFetch(
    `/v1/projects/${projectId}/ai-models/${encodeURIComponent(modelConfigId)}/availability`,
    {
      method: 'PUT',
      body: JSON.stringify({ enabled }),
    },
  )
}

export async function putProjectAiModelCredentialOverride(
  projectId: number,
  modelConfigId: string,
  body: { api_key: string; api_base?: string | null },
): Promise<ProjectEffectiveAiModelRow> {
  return jsonFetch(
    `/v1/projects/${projectId}/ai-models/${encodeURIComponent(modelConfigId)}/credential-override`,
    {
      method: 'PUT',
      body: JSON.stringify(body),
    },
  )
}

export async function deleteProjectAiModelCredentialOverride(
  projectId: number,
  modelConfigId: string,
): Promise<ProjectEffectiveAiModelRow> {
  return jsonFetch(
    `/v1/projects/${projectId}/ai-models/${encodeURIComponent(modelConfigId)}/credential-override`,
    { method: 'DELETE' },
  )
}

export interface ProjectAiModelDefaultRole {
  role: string
  model_config_id: string
}

export async function fetchProjectAiModelDefaults(
  projectId: number,
): Promise<ProjectAiModelDefaultRole[]> {
  return jsonFetch(`/v1/projects/${projectId}/ai-model-defaults`)
}

export async function fetchProjectSemanticIndexingConfigured(
  projectId: number,
): Promise<{ configured: boolean }> {
  return jsonFetch(`/v1/projects/${projectId}/semantic-indexing-configured`)
}

export async function putProjectAiModelDefaultRole(
  projectId: number,
  role: string,
  modelConfigId: string,
): Promise<ProjectAiModelDefaultRole> {
  return jsonFetch(
    `/v1/projects/${projectId}/ai-model-defaults/${encodeURIComponent(role)}`,
    {
      method: 'PUT',
      body: JSON.stringify({ model_config_id: modelConfigId }),
    },
  )
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

export interface MapDefaultViewport {
  lat: number
  lng: number
  zoom: number
}

export interface OrganizationSettings {
  map_default_viewport: MapDefaultViewport | null
}

export async function getOrganizationSettings(
  orgId: number,
): Promise<OrganizationSettings> {
  return jsonFetch(`/v1/organizations/${orgId}/settings`)
}

export async function patchOrganizationSettings(
  orgId: number,
  body: { map_default_viewport: MapDefaultViewport | null },
): Promise<OrganizationSettings> {
  return jsonFetch(`/v1/organizations/${orgId}/settings`, {
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

export interface WorkspaceProjectDeletePreview {
  project_id: number
  name: string
  slug: string
  flow_count: number
  run_count: number
  processed_item_count: number
  article_count: number
  api_credential_count: number
  secret_count: number
}

export interface WorkspaceDeletePreview {
  workspace_id: number
  name: string
  slug: string
  project_count: number
  flow_count: number
  run_count: number
  processed_item_count: number
  article_count: number
  api_credential_count: number
  secret_count: number
  projects: WorkspaceProjectDeletePreview[]
}

export async function getWorkspaceDeletePreview(
  orgId: number,
  workspaceId: number,
): Promise<WorkspaceDeletePreview> {
  return jsonFetch(
    `/v1/organizations/${orgId}/workspaces/${workspaceId}/delete-preview`,
  )
}

export async function deleteWorkspace(
  orgId: number,
  workspaceId: number,
  confirmName: string,
): Promise<void> {
  await jsonFetch(`/v1/organizations/${orgId}/workspaces/${workspaceId}/delete`, {
    method: "POST",
    body: JSON.stringify({ confirm_name: confirmName }),
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
  scopes: string[]
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
  body: {
    credential_type: 'user' | 'service'
    label?: string | null
    scopes?: string[]
  },
): Promise<ProjectAccessCredentialCreated> {
  return jsonFetch(`/v1/projects/${projectId}/api-keys`, {
    method: 'POST',
    body: JSON.stringify({
      credential_type: body.credential_type,
      label: body.label ?? null,
      ...(body.scopes?.length ? { scopes: body.scopes } : {}),
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

/** Webhook endpoints (org admin): send updates to another application when things happen. */
export type WebhookOutcome = 'succeeded' | 'failed'

export interface WebhookFlow {
  flow_id: string
  flow_name: string | null
}

export interface WebhookEventType {
  event_type: string
  /** Flow-scoped types can target specific flows; others always apply to the whole project. */
  flow_scoped: boolean
}

export interface WebhookEndpoint {
  id: string
  project_id: number
  project_name: string | null
  project_slug: string | null
  name: string
  destination_host: string
  status: string
  secret_version: number
  verified_at: string | null
  paused_at: string | null
  pause_reason: string | null
  last_success_at: string | null
  last_failure_at: string | null
  outcomes: WebhookOutcome[] | null
  event_types: string[]
  /** True when flow-scoped notifications apply to every flow in the project. */
  all_flows: boolean
  flows: WebhookFlow[]
  pending_deliveries: number
  failed_deliveries: number
  created_at: string
  updated_at: string
}

export interface WebhookEndpointCreated {
  endpoint: WebhookEndpoint
  /** Shown exactly once; store it in the receiving application. */
  signing_secret: string
}

export interface WebhookSecret {
  signing_secret: string
  secret_version: number
  endpoint: WebhookEndpoint
}

export interface WebhookTestResult {
  ok: boolean
  status_code: number | null
  failure_category: string | null
  failure_summary: string | null
}

export interface WebhookTestResponse {
  result: WebhookTestResult
  endpoint: WebhookEndpoint
}

export interface WebhookDeliveryAttempt {
  attempt_number: number
  attempted_at: string
  status_code: number | null
  failure_category: string | null
  failure_summary: string | null
  duration_ms: number | null
}

export interface WebhookDelivery {
  id: string
  event_id: string
  event_type: string
  flow_name: string | null
  run_id: string | null
  state: string
  attempt_count: number
  next_attempt_at: string | null
  last_status_code: number | null
  failure_category: string | null
  failure_summary: string | null
  is_replay: boolean
  is_test: boolean
  created_at: string
  delivered_at: string | null
  attempts: WebhookDeliveryAttempt[]
}

export async function listOrganizationWebhookEndpoints(
  orgId: number,
  projectId?: number,
): Promise<WebhookEndpoint[]> {
  const q = projectId != null ? `?project_id=${projectId}` : ''
  return jsonFetch(`/v1/organizations/${orgId}/webhook-endpoints${q}`)
}

export interface WebhookEndpointCreateInput {
  project_id: number
  name: string
  url: string
  event_types: string[]
  flow_ids?: string[]
  all_flows?: boolean
  outcomes?: WebhookOutcome[] | null
}

export async function listOrganizationWebhookEventTypes(
  orgId: number,
): Promise<WebhookEventType[]> {
  return jsonFetch(`/v1/organizations/${orgId}/webhook-event-types`)
}

export async function createOrganizationWebhookEndpoint(
  orgId: number,
  body: WebhookEndpointCreateInput,
): Promise<WebhookEndpointCreated> {
  return jsonFetch(`/v1/organizations/${orgId}/webhook-endpoints`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export interface WebhookEndpointPatchInput {
  name?: string
  url?: string
  event_types?: string[]
  flow_ids?: string[]
  all_flows?: boolean
  outcomes?: WebhookOutcome[] | null
  clear_outcomes?: boolean
}

export async function patchOrganizationWebhookEndpoint(
  orgId: number,
  endpointId: string,
  body: WebhookEndpointPatchInput,
): Promise<WebhookEndpoint> {
  return jsonFetch(
    `/v1/organizations/${orgId}/webhook-endpoints/${encodeURIComponent(endpointId)}`,
    { method: 'PATCH', body: JSON.stringify(body) },
  )
}

export async function deleteOrganizationWebhookEndpoint(
  orgId: number,
  endpointId: string,
): Promise<void> {
  await jsonFetch(
    `/v1/organizations/${orgId}/webhook-endpoints/${encodeURIComponent(endpointId)}`,
    { method: 'DELETE' },
  )
}

export async function disableOrganizationWebhookEndpoint(
  orgId: number,
  endpointId: string,
): Promise<WebhookEndpoint> {
  return jsonFetch(
    `/v1/organizations/${orgId}/webhook-endpoints/${encodeURIComponent(endpointId)}/disable`,
    { method: 'POST' },
  )
}

export async function activateOrganizationWebhookEndpoint(
  orgId: number,
  endpointId: string,
): Promise<WebhookEndpoint> {
  return jsonFetch(
    `/v1/organizations/${orgId}/webhook-endpoints/${encodeURIComponent(endpointId)}/activate`,
    { method: 'POST' },
  )
}

export async function rotateOrganizationWebhookSecret(
  orgId: number,
  endpointId: string,
): Promise<WebhookSecret> {
  return jsonFetch(
    `/v1/organizations/${orgId}/webhook-endpoints/${encodeURIComponent(endpointId)}/rotate-secret`,
    { method: 'POST' },
  )
}

export async function testOrganizationWebhookEndpoint(
  orgId: number,
  endpointId: string,
): Promise<WebhookTestResponse> {
  return jsonFetch(
    `/v1/organizations/${orgId}/webhook-endpoints/${encodeURIComponent(endpointId)}/test`,
    { method: 'POST' },
  )
}

export async function listOrganizationWebhookDeliveries(
  orgId: number,
  endpointId: string,
  limit = 50,
): Promise<WebhookDelivery[]> {
  return jsonFetch(
    `/v1/organizations/${orgId}/webhook-endpoints/${encodeURIComponent(endpointId)}/deliveries?limit=${limit}`,
  )
}

export async function replayOrganizationWebhookDelivery(
  orgId: number,
  endpointId: string,
  deliveryId: string,
): Promise<{ delivery_id: string }> {
  return jsonFetch(
    `/v1/organizations/${orgId}/webhook-endpoints/${encodeURIComponent(endpointId)}/deliveries/${encodeURIComponent(deliveryId)}/replay`,
    { method: 'POST' },
  )
}
