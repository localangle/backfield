import { parseOpenApiDocument, type OpenApiDocument } from "./openapi"
import type { TypeaheadKind } from "./presentation"

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

export interface IdCandidate {
  id: string
  label: string
  subtitle: string
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

function optionalText(record: Record<string, unknown>, key: string): string | undefined {
  const value = record[key]
  return typeof value === "string" && value.trim() ? value.trim() : undefined
}

function candidateSubtitle(
  kind: TypeaheadKind,
  item: Record<string, unknown>,
): string {
  if (kind === "person") {
    return [
      optionalText(item, "title"),
      optionalText(item, "affiliation"),
      optionalText(item, "person_type"),
    ].filter(Boolean).join(" · ") || "Person"
  }
  if (kind === "location") {
    return [
      optionalText(item, "formatted_address"),
      optionalText(item, "location_type"),
    ].filter(Boolean).join(" · ") || "Location"
  }
  if (kind === "organization") {
    return optionalText(item, "organization_type") ?? "Organization"
  }
  if (kind === "article") {
    const source = item.source
    const sourceName =
      source && typeof source === "object"
        ? optionalText(source as Record<string, unknown>, "name")
        : undefined
    return [
      optionalText(item, "pub_date"),
      optionalText(item, "author"),
      sourceName,
    ].filter(Boolean).join(" · ") || "Article"
  }
  const article = item.article
  const headline =
    article && typeof article === "object"
      ? optionalText(article as Record<string, unknown>, "headline")
      : undefined
  return [
    optionalText(item, "entity_type"),
    optionalText(item, "nature"),
    headline,
  ].filter(Boolean).join(" · ") || "Mention"
}

export async function searchIdCandidates(
  origin: string,
  projectSlug: string,
  apiKey: string,
  kind: TypeaheadKind,
  query: string,
  entityType?: string,
  signal?: AbortSignal,
): Promise<IdCandidate[]> {
  const resource: Record<TypeaheadKind, string> = {
    article: "articles",
    location: "locations",
    mention: "mentions",
    organization: "organizations",
    person: "people",
  }
  const search = new URLSearchParams({
    q: query,
    limit: "10",
    offset: "0",
  })
  if (kind === "person" || kind === "location" || kind === "organization") {
    search.set("min_mentions", "0")
  }
  if (kind === "mention" && entityType) search.set("entity_type", entityType)
  const payload = (await publicJson(
    origin,
    `/public/v1/projects/${encodeURIComponent(projectSlug)}/${resource[kind]}/search?${search}`,
    apiKey,
    signal,
  )) as Record<string, unknown>
  if (!Array.isArray(payload.items)) {
    throw new Error(`${kind} search response was invalid.`)
  }
  return payload.items.flatMap((rawItem) => {
    if (!rawItem || typeof rawItem !== "object") return []
    const item = rawItem as Record<string, unknown>
    const rawId = kind === "mention" ? item.mention_id : item.id
    const rawLabel = kind === "article" ? item.headline : item.label
    if (
      (typeof rawId !== "string" && typeof rawId !== "number") ||
      typeof rawLabel !== "string"
    ) {
      return []
    }
    return [{
      id: String(rawId),
      label: rawLabel,
      subtitle: candidateSubtitle(kind, item),
    }]
  })
}
