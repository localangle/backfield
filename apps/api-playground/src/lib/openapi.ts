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
  description?: string
  default?: unknown
  example?: unknown
  enum?: unknown[]
  items?: OpenApiSchema | OpenApiReference
  properties?: Record<string, OpenApiSchema | OpenApiReference>
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
const groupOrder = [
  "Project",
  "Articles",
  "Mentions",
  "Locations",
  "Organizations",
  "People",
  "Runs",
  "Other",
]

function compactPath(path: string): string {
  if (!path.startsWith(publicProjectPrefix)) {
    return path
  }
  const relative = path.slice(publicProjectPrefix.length).replace(/\/$/, "")
  return relative || "/project"
}

function resourceGroup(path: string): string {
  const firstSegment = compactPath(path).split("/").filter(Boolean)[0]
  const knownGroups: Record<string, string> = {
    project: "Project",
    articles: "Articles",
    mentions: "Mentions",
    locations: "Locations",
    organizations: "Organizations",
    people: "People",
    runs: "Runs",
  }
  return knownGroups[firstSegment ?? ""] ?? "Other"
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

      operations.push({
        id: operation.operationId ?? `${method}:${path}`,
        method,
        path,
        displayPath: compactPath(path),
        summary: friendlySummary(
          operation.summary ?? operation.operationId ?? `${method.toUpperCase()} ${path}`,
        ),
        description: operation.description,
        group: resourceGroup(path),
        parameters,
        requestBody: resolveRequestBody(document, operation.requestBody),
      })
    }
  }

  return operations.sort((left, right) => {
    return (
      groupOrder.indexOf(left.group) - groupOrder.indexOf(right.group) ||
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
    const item = exampleForSchema(document, schema.items, depth + 1)
    return item === undefined ? [] : [item]
  }
  if (schema.type === "object" || schema.properties) {
    return Object.fromEntries(
      Object.entries(schema.properties ?? {}).map(([name, property]) => [
        name,
        exampleForSchema(document, property, depth + 1) ?? null,
      ]),
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
