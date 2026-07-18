export type HttpMethod =
  | "delete"
  | "get"
  | "head"
  | "options"
  | "patch"
  | "post"
  | "put"
  | "trace"

export interface OpenApiSchema {
  type?: string
  format?: string
  title?: string
  description?: string
  default?: unknown
  example?: unknown
  enum?: unknown[]
  minimum?: number
  maximum?: number
  minLength?: number
  maxLength?: number
  minItems?: number
  maxItems?: number
  uniqueItems?: boolean
  pattern?: string
  items?: OpenApiSchema | OpenApiReference
  properties?: Record<string, OpenApiSchema | OpenApiReference>
  additionalProperties?: boolean | OpenApiSchema | OpenApiReference
  required?: string[]
  nullable?: boolean
  oneOf?: Array<OpenApiSchema | OpenApiReference>
  anyOf?: Array<OpenApiSchema | OpenApiReference>
  allOf?: Array<OpenApiSchema | OpenApiReference>
}

export interface OpenApiReference {
  $ref: string
}

export interface OpenApiParameter {
  name: string
  in: "path" | "query" | "header" | "cookie"
  description?: string
  required?: boolean
  schema?: OpenApiSchema | OpenApiReference
  example?: unknown
}

interface OpenApiMediaType {
  schema?: OpenApiSchema | OpenApiReference
  example?: unknown
}

interface OpenApiRequestBody {
  description?: string
  required?: boolean
  content?: Record<string, OpenApiMediaType>
}

interface OpenApiOperation {
  operationId?: string
  summary?: string
  description?: string
  tags?: string[]
  parameters?: Array<OpenApiParameter | OpenApiReference>
  requestBody?: OpenApiRequestBody | OpenApiReference
}

interface OpenApiPathItem {
  parameters?: Array<OpenApiParameter | OpenApiReference>
  [key: string]: unknown
}

export interface OpenApiDocument {
  openapi: string
  info: {
    title: string
    version: string
    description?: string
  }
  paths: Record<string, OpenApiPathItem>
  components?: Record<string, unknown>
}

export interface PlaygroundOperation {
  id: string
  method: HttpMethod
  path: string
  displayPath: string
  summary: string
  description?: string
  group: string
  /** Sort key within `group`; matches Backfield API docs nav order. */
  groupOrder: number
  parameters: OpenApiParameter[]
  requestBody?: OpenApiRequestBody
}

const httpMethods = new Set<HttpMethod>([
  "delete",
  "get",
  "head",
  "options",
  "patch",
  "post",
  "put",
  "trace",
])

const publicProjectPrefix = "/public/v1/projects/{project_slug}"

/** Top-level groups and order match the Backfield API docs nav (`mkdocs-api.yml`). */
const groupOrder = [
  "Projects",
  "Metadata",
  "Articles",
  "Mentions",
  "People",
  "Locations",
  "Organizations",
  "Other",
] as const

type DocsGroup = (typeof groupOrder)[number]

interface DocsPresentation {
  group: DocsGroup
  summary: string
  /** Stable order within the group, matching docs nav. */
  order: number
  match: (method: HttpMethod, displayPath: string) => boolean
}

function isEntityResourcePath(displayPath: string, resource: string, suffix: string): boolean {
  return new RegExp(`^/${resource}/\\{[^}]+\\}${suffix}$`).test(displayPath)
}

function isArticleIdPath(displayPath: string, suffix: string): boolean {
  return new RegExp(`^/articles/\\{[^}]+\\}${suffix}$`).test(displayPath)
}

/**
 * Docs-facing labels and group membership for public operations.
 * Order within each group follows the API Reference nav.
 */
const docsPresentations: DocsPresentation[] = [
  // Projects
  {
    group: "Projects",
    summary: "Get project",
    order: 0,
    match: (_method, displayPath) => displayPath === "/project",
  },

  // Metadata (facets live here in docs; article metadata endpoints stay under Articles)
  {
    group: "Metadata",
    summary: "Article facets",
    order: 0,
    match: (method, displayPath) => method === "get" && displayPath === "/articles/facets",
  },
  {
    group: "Metadata",
    summary: "Mention facets",
    order: 1,
    match: (method, displayPath) => method === "get" && displayPath === "/mentions/facets",
  },

  // Articles
  {
    group: "Articles",
    summary: "Get article",
    order: 0,
    match: (method, displayPath) => method === "get" && isArticleIdPath(displayPath, ""),
  },
  {
    group: "Articles",
    summary: "List and search",
    order: 1,
    match: (method, displayPath) => method === "get" && displayPath === "/articles/search",
  },
  {
    group: "Articles",
    summary: "Semantic search",
    order: 2,
    match: (method, displayPath) => method === "post" && displayPath === "/articles/semantic-search",
  },
  {
    group: "Articles",
    summary: "Geographic search",
    order: 3,
    match: (method, displayPath) => method === "get" && displayPath === "/articles/geo-search",
  },
  {
    group: "Articles",
    summary: "List metadata types",
    order: 4,
    match: (method, displayPath) => method === "get" && displayPath === "/articles/metadata/types",
  },
  {
    group: "Articles",
    summary: "List metadata values",
    order: 5,
    match: (method, displayPath) =>
      method === "get" &&
      /^\/articles\/metadata\/types\/\{[^}]+\}\/values$/.test(displayPath),
  },
  {
    group: "Articles",
    summary: "Get article metadata",
    order: 6,
    match: (method, displayPath) => method === "get" && isArticleIdPath(displayPath, "/metadata"),
  },
  {
    group: "Articles",
    summary: "List mentions",
    order: 7,
    match: (method, displayPath) => method === "get" && isArticleIdPath(displayPath, "/mentions"),
  },
  {
    group: "Articles",
    summary: "List people",
    order: 8,
    match: (method, displayPath) => method === "get" && isArticleIdPath(displayPath, "/people"),
  },
  {
    group: "Articles",
    summary: "List organizations",
    order: 9,
    match: (method, displayPath) =>
      method === "get" && isArticleIdPath(displayPath, "/organizations"),
  },
  {
    group: "Articles",
    summary: "List locations",
    order: 10,
    match: (method, displayPath) => method === "get" && isArticleIdPath(displayPath, "/locations"),
  },
  {
    group: "Articles",
    summary: "List custom records",
    order: 11,
    match: (method, displayPath) =>
      method === "get" && isArticleIdPath(displayPath, "/custom-records"),
  },
  {
    group: "Articles",
    summary: "List images",
    order: 12,
    match: (method, displayPath) => method === "get" && isArticleIdPath(displayPath, "/images"),
  },

  // Mentions
  {
    group: "Mentions",
    summary: "Get mention",
    order: 0,
    match: (method, displayPath) =>
      method === "get" && /^\/mentions\/\{[^}]+\}\/\{[^}]+\}$/.test(displayPath),
  },
  {
    group: "Mentions",
    summary: "List and search",
    order: 1,
    match: (method, displayPath) => method === "get" && displayPath === "/mentions/search",
  },

  // People (Entities → People in docs)
  {
    group: "People",
    summary: "Get person",
    order: 0,
    match: (method, displayPath) =>
      method === "get" && isEntityResourcePath(displayPath, "people", ""),
  },
  {
    group: "People",
    summary: "List and search",
    order: 1,
    match: (method, displayPath) =>
      method === "get" && (displayPath === "/people" || displayPath === "/people/search"),
  },
  {
    group: "People",
    summary: "List types",
    order: 2,
    match: (method, displayPath) => method === "get" && displayPath === "/people/types",
  },
  {
    group: "People",
    summary: "List articles",
    order: 3,
    match: (method, displayPath) =>
      method === "get" && isEntityResourcePath(displayPath, "people", "/articles"),
  },
  {
    group: "People",
    summary: "List mentions",
    order: 4,
    match: (method, displayPath) =>
      method === "get" && isEntityResourcePath(displayPath, "people", "/mentions"),
  },
  {
    group: "People",
    summary: "List connections",
    order: 5,
    match: (method, displayPath) =>
      method === "get" && isEntityResourcePath(displayPath, "people", "/connections"),
  },

  // Locations (Entities → Locations in docs)
  {
    group: "Locations",
    summary: "Get location",
    order: 0,
    match: (method, displayPath) =>
      method === "get" && isEntityResourcePath(displayPath, "locations", ""),
  },
  {
    group: "Locations",
    summary: "List and search",
    order: 1,
    match: (method, displayPath) =>
      method === "get" &&
      (displayPath === "/locations" || displayPath === "/locations/search"),
  },
  {
    group: "Locations",
    summary: "List types",
    order: 2,
    match: (method, displayPath) => method === "get" && displayPath === "/locations/types",
  },
  {
    group: "Locations",
    summary: "Geographic search",
    order: 3,
    match: (method, displayPath) => method === "get" && displayPath === "/locations/geo-search",
  },
  {
    group: "Locations",
    summary: "List articles",
    order: 4,
    match: (method, displayPath) =>
      method === "get" && isEntityResourcePath(displayPath, "locations", "/articles"),
  },
  {
    group: "Locations",
    summary: "List mentions",
    order: 5,
    match: (method, displayPath) =>
      method === "get" && isEntityResourcePath(displayPath, "locations", "/mentions"),
  },
  {
    group: "Locations",
    summary: "List connections",
    order: 6,
    match: (method, displayPath) =>
      method === "get" && isEntityResourcePath(displayPath, "locations", "/connections"),
  },

  // Organizations (Entities → Organizations in docs)
  {
    group: "Organizations",
    summary: "Get organization",
    order: 0,
    match: (method, displayPath) =>
      method === "get" && isEntityResourcePath(displayPath, "organizations", ""),
  },
  {
    group: "Organizations",
    summary: "List and search",
    order: 1,
    match: (method, displayPath) =>
      method === "get" &&
      (displayPath === "/organizations" || displayPath === "/organizations/search"),
  },
  {
    group: "Organizations",
    summary: "List types",
    order: 2,
    match: (method, displayPath) => method === "get" && displayPath === "/organizations/types",
  },
  {
    group: "Organizations",
    summary: "List articles",
    order: 3,
    match: (method, displayPath) =>
      method === "get" && isEntityResourcePath(displayPath, "organizations", "/articles"),
  },
  {
    group: "Organizations",
    summary: "List mentions",
    order: 4,
    match: (method, displayPath) =>
      method === "get" && isEntityResourcePath(displayPath, "organizations", "/mentions"),
  },
  {
    group: "Organizations",
    summary: "List connections",
    order: 5,
    match: (method, displayPath) =>
      method === "get" && isEntityResourcePath(displayPath, "organizations", "/connections"),
  },

  // Other (Mention timeline, Geo cells, Runs)
  {
    group: "Other",
    summary: "Get timeline",
    order: 0,
    match: (method, displayPath) =>
      method === "get" &&
      (isEntityResourcePath(displayPath, "people", "/mentions/timeline") ||
        isEntityResourcePath(displayPath, "locations", "/mentions/timeline") ||
        isEntityResourcePath(displayPath, "organizations", "/mentions/timeline")),
  },
  {
    group: "Other",
    summary: "Coverage",
    order: 1,
    match: (method, displayPath) => method === "get" && displayPath === "/articles/geo-cells",
  },
  {
    group: "Other",
    summary: "List articles",
    order: 2,
    match: (method, displayPath) =>
      method === "get" && /^\/articles\/geo-cells\/\{[^}]+\}$/.test(displayPath),
  },
  {
    group: "Other",
    summary: "Batch query",
    order: 3,
    match: (method, displayPath) =>
      method === "post" && displayPath === "/articles/geo-cells/query",
  },
  {
    group: "Other",
    summary: "Trigger run",
    order: 4,
    match: (method, displayPath) => method === "post" && displayPath === "/runs",
  },
  {
    group: "Other",
    summary: "Get run",
    order: 5,
    match: (method, displayPath) =>
      method === "get" && /^\/runs\/\{[^}]+\}$/.test(displayPath),
  },
]

function compactPath(path: string): string {
  if (!path.startsWith(publicProjectPrefix)) {
    return path.replace(/\/$/, "") || path
  }
  const relative = path.slice(publicProjectPrefix.length).replace(/\/$/, "")
  return relative || "/project"
}

function friendlySummary(summary: string): string {
  return summary
    .replace(/\bPublic\s+/g, "")
    .replace(
      /\bProject\s+(?=(?:Article|Mention|Location|Organization|Person|Run)s?\b)/g,
      "",
    )
    .replace(/\s+/g, " ")
    .trim()
}

function presentOperation(
  method: HttpMethod,
  displayPath: string,
  openApiSummary: string,
): { group: string; summary: string; order: number } {
  const matched = docsPresentations.find((presentation) =>
    presentation.match(method, displayPath),
  )
  if (matched) {
    return {
      group: matched.group,
      summary: matched.summary,
      order: matched.order,
    }
  }
  return {
    group: "Other",
    summary: friendlySummary(openApiSummary),
    order: 1000,
  }
}


function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

function isReference(value: unknown): value is OpenApiReference {
  return isRecord(value) && typeof value.$ref === "string"
}

function resolveReference(document: OpenApiDocument, reference: OpenApiReference): unknown {
  if (!reference.$ref.startsWith("#/")) {
    return undefined
  }

  return reference.$ref
    .slice(2)
    .split("/")
    .map((part) => part.split("~1").join("/").split("~0").join("~"))
    .reduce<unknown>((current, part) => {
      return isRecord(current) ? current[part] : undefined
    }, document)
}

export function resolveSchema(
  document: OpenApiDocument,
  schema: OpenApiSchema | OpenApiReference | undefined,
): OpenApiSchema | undefined {
  if (!schema) {
    return undefined
  }
  if (!isReference(schema)) {
    return schema
  }
  const resolved = resolveReference(document, schema)
  return isRecord(resolved) ? (resolved as OpenApiSchema) : undefined
}

/**
 * Resolve the concrete, non-null schema used by a form control. FastAPI emits
 * optional values as `anyOf: [<type>, null]`, often with a component reference.
 */
export function resolveInputSchema(
  document: OpenApiDocument,
  rawSchema: OpenApiSchema | OpenApiReference | undefined,
): OpenApiSchema | undefined {
  const schema = resolveSchema(document, rawSchema)
  if (!schema) return undefined

  const alternatives = schema.anyOf ?? schema.oneOf
  if (!alternatives) return schema

  for (const alternative of alternatives) {
    const resolved = resolveSchema(document, alternative)
    if (resolved && resolved.type !== "null") {
      return {
        ...schema,
        ...resolved,
        description: schema.description ?? resolved.description,
        title: schema.title ?? resolved.title,
      }
    }
  }
  return schema
}

function resolveParameter(
  document: OpenApiDocument,
  parameter: OpenApiParameter | OpenApiReference,
): OpenApiParameter | undefined {
  const resolved = isReference(parameter) ? resolveReference(document, parameter) : parameter
  if (
    !isRecord(resolved) ||
    typeof resolved.name !== "string" ||
    !["path", "query", "header", "cookie"].includes(String(resolved.in))
  ) {
    return undefined
  }
  return resolved as unknown as OpenApiParameter
}

function resolveRequestBody(
  document: OpenApiDocument,
  requestBody: OpenApiRequestBody | OpenApiReference | undefined,
): OpenApiRequestBody | undefined {
  if (!requestBody) {
    return undefined
  }
  const resolved = isReference(requestBody) ? resolveReference(document, requestBody) : requestBody
  return isRecord(resolved) ? (resolved as OpenApiRequestBody) : undefined
}

export function parseOpenApiDocument(value: unknown): OpenApiDocument {
  if (
    !isRecord(value) ||
    typeof value.openapi !== "string" ||
    !isRecord(value.info) ||
    typeof value.info.title !== "string" ||
    typeof value.info.version !== "string" ||
    !isRecord(value.paths)
  ) {
    throw new Error("The server returned an invalid OpenAPI document.")
  }
  return value as unknown as OpenApiDocument
}

export function listOperations(document: OpenApiDocument): PlaygroundOperation[] {
  const operations: PlaygroundOperation[] = []

  for (const [path, pathItem] of Object.entries(document.paths)) {
    if (!isRecord(pathItem)) {
      continue
    }
    const sharedParameters = Array.isArray(pathItem.parameters) ? pathItem.parameters : []

    for (const [candidateMethod, candidateOperation] of Object.entries(pathItem)) {
      const method = candidateMethod.toLowerCase() as HttpMethod
      if (!httpMethods.has(method) || !isRecord(candidateOperation)) {
        continue
      }
      const operation = candidateOperation as unknown as OpenApiOperation
      const ownParameters = Array.isArray(operation.parameters) ? operation.parameters : []
      const merged = [...sharedParameters, ...ownParameters]
        .map((parameter) => resolveParameter(document, parameter))
        .filter((parameter): parameter is OpenApiParameter => parameter !== undefined)
      const parameters = Array.from(
        new Map(merged.map((parameter) => [`${parameter.in}:${parameter.name}`, parameter])).values(),
      )

      const displayPath = compactPath(path)
      const presentation = presentOperation(
        method,
        displayPath,
        operation.summary ?? operation.operationId ?? `${method.toUpperCase()} ${path}`,
      )

      operations.push({
        id: operation.operationId ?? `${method}:${path}`,
        method,
        path,
        displayPath,
        summary: presentation.summary,
        description: operation.description,
        group: presentation.group,
        groupOrder: presentation.order,
        parameters,
        requestBody: resolveRequestBody(document, operation.requestBody),
      })
    }
  }

  return operations.sort((left, right) => {
    return (
      groupOrder.indexOf(left.group as (typeof groupOrder)[number]) -
        groupOrder.indexOf(right.group as (typeof groupOrder)[number]) ||
      left.groupOrder - right.groupOrder ||
      left.displayPath.localeCompare(right.displayPath) ||
      left.method.localeCompare(right.method)
    )
  })
}

export function jsonBodySchema(
  operation: PlaygroundOperation,
): OpenApiSchema | OpenApiReference | undefined {
  return operation.requestBody?.content?.["application/json"]?.schema
}

export function exampleForSchema(
  document: OpenApiDocument,
  rawSchema: OpenApiSchema | OpenApiReference | undefined,
  depth = 0,
): unknown {
  const schema = resolveSchema(document, rawSchema)
  if (!schema || depth > 6) {
    return undefined
  }
  if (schema.example !== undefined) {
    return schema.example
  }
  if (schema.default !== undefined) {
    return schema.default
  }
  if (schema.enum?.length) {
    return schema.enum[0]
  }

  const combined = schema.allOf?.[0] ?? schema.oneOf?.[0] ?? schema.anyOf?.[0]
  if (combined) {
    return exampleForSchema(document, combined, depth + 1)
  }
  if (schema.type === "array") {
    return []
  }
  if (schema.type === "object" || schema.properties) {
    const required = new Set(schema.required ?? [])
    return Object.fromEntries(
      Object.entries(schema.properties ?? {}).flatMap(([name, property]) => {
        const propertySchema = resolveSchema(document, property)
        const hasStarterValue =
          required.has(name) ||
          propertySchema?.example !== undefined ||
          propertySchema?.default !== undefined
        return hasStarterValue
          ? [[name, exampleForSchema(document, property, depth + 1) ?? ""]]
          : []
      }),
    )
  }
  if (schema.type === "boolean") {
    return false
  }
  if (schema.type === "integer" || schema.type === "number") {
    return 0
  }
  return ""
}
