import { parseOpenApiDocument, type OpenApiDocument } from "./openapi"

export interface ArticleFacets {
  authors: string[]
  externalSources: string[]
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

export async function fetchArticleFacets(
  origin: string,
  projectSlug: string,
  apiKey: string,
  signal?: AbortSignal,
): Promise<ArticleFacets> {
  const response = await fetch(
    `${origin}/public/v1/projects/${encodeURIComponent(projectSlug)}/articles/facets`,
    {
      method: "GET",
      credentials: "omit",
      headers: {
        Accept: "application/json",
        Authorization: `Bearer ${apiKey}`,
      },
      referrerPolicy: "no-referrer",
      signal,
    },
  )
  if (!response.ok) {
    throw new Error(`Article filter values request failed with ${response.status}.`)
  }

  const payload = (await response.json()) as Record<string, unknown>
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
