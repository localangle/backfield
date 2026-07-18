import { parseOpenApiDocument, type OpenApiDocument } from "./openapi"

export interface ArticleFacets {
  authors: string[]
  externalSources: string[]
}

export interface MentionFacets {
  entityTypes: string[]
  natures: string[]
  locationTypes: string[]
  personTypes: string[]
  organizationTypes: string[]
}

export async function fetchPublicSchema(origin: string): Promise<OpenApiDocument> {
  const response = await fetch(`${origin}/public/v1/openapi.json`, {
    method: "GET",
    credentials: "omit",
    headers: { Accept: "application/json" },
    referrerPolicy: "no-referrer",
  })
  if (!response.ok) {
    throw new Error(`Schema request failed with ${response.status} ${response.statusText}.`)
  }
  return parseOpenApiDocument(await response.json())
}

export async function fetchArticleMetaTypes(
  origin: string,
  projectSlug: string,
  apiKey: string,
  signal?: AbortSignal,
): Promise<string[]> {
  const payload = await publicJson(
    origin,
    `/public/v1/projects/${encodeURIComponent(projectSlug)}/articles/metadata/types`,
    apiKey,
    signal,
  )
  const metaTypes = (payload as Record<string, unknown>).meta_types
  if (!Array.isArray(metaTypes) || !metaTypes.every((value) => typeof value === "string")) {
    throw new Error("Metadata types response was invalid.")
  }
  return metaTypes
}

export async function fetchArticleMetaValues(
  origin: string,
  projectSlug: string,
  metaType: string,
  apiKey: string,
  signal?: AbortSignal,
): Promise<string[]> {
  const payload = await publicJson(
    origin,
    `/public/v1/projects/${encodeURIComponent(projectSlug)}/articles/metadata/types/${encodeURIComponent(metaType)}/values`,
    apiKey,
    signal,
  )
  const values = (payload as Record<string, unknown>).values
  if (!Array.isArray(values) || !values.every((value) => typeof value === "string")) {
    throw new Error("Metadata values response was invalid.")
  }
  return values
}

async function publicJson(
  origin: string,
  path: string,
  apiKey: string,
  signal?: AbortSignal,
): Promise<unknown> {
  const response = await fetch(`${origin}${path}`, {
    method: "GET",
    credentials: "omit",
    headers: {
      Accept: "application/json",
      Authorization: `Bearer ${apiKey}`,
    },
    referrerPolicy: "no-referrer",
    signal,
  })
  if (!response.ok) {
    throw new Error(`Request failed with ${response.status}.`)
  }
  return await response.json()
}

export async function fetchArticleFacets(
  origin: string,
  projectSlug: string,
  apiKey: string,
  signal?: AbortSignal,
): Promise<ArticleFacets> {
  const payload = (await publicJson(
    origin,
    `/public/v1/projects/${encodeURIComponent(projectSlug)}/articles/facets`,
    apiKey,
    signal,
  )) as Record<string, unknown>
  if (
    !Array.isArray(payload.authors) ||
    !payload.authors.every((value) => typeof value === "string") ||
    !Array.isArray(payload.external_sources) ||
    !payload.external_sources.every((value) => typeof value === "string")
  ) {
    throw new Error("Article filter values response was invalid.")
  }
  return {
    authors: payload.authors,
    externalSources: payload.external_sources,
  }
}

function stringArray(
  payload: Record<string, unknown>,
  key: string,
  responseName: string,
): string[] {
  const value = payload[key]
  if (!Array.isArray(value) || !value.every((item) => typeof item === "string")) {
    throw new Error(`${responseName} response was invalid.`)
  }
  return value
}

export async function fetchMentionFacets(
  origin: string,
  projectSlug: string,
  apiKey: string,
  signal?: AbortSignal,
): Promise<MentionFacets> {
  const payload = (await publicJson(
    origin,
    `/public/v1/projects/${encodeURIComponent(projectSlug)}/mentions/facets`,
    apiKey,
    signal,
  )) as Record<string, unknown>
  return {
    entityTypes: stringArray(payload, "entity_types", "Mention facets"),
    natures: stringArray(payload, "natures", "Mention facets"),
    locationTypes: stringArray(payload, "location_types", "Mention facets"),
    personTypes: stringArray(payload, "person_types", "Mention facets"),
    organizationTypes: stringArray(payload, "organization_types", "Mention facets"),
  }
}
