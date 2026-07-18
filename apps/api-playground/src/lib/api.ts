import { parseOpenApiDocument, type OpenApiDocument } from "./openapi"

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
