import {
  type OpenApiDocument,
  type OpenApiParameter,
  type OpenApiReference,
  type OpenApiSchema,
  type PlaygroundOperation,
  jsonBodySchema,
  resolveInputSchema,
} from "./openapi"

export type ParameterValues = Record<string, string>

export interface PreparedRequest {
  url: string
  init: RequestInit
  curl: string
}

export interface PlaygroundResponse {
  status: number
  statusText: string
  headers: Array<[string, string]>
  body: string
  requestId?: string
}

function parameterKey(parameter: OpenApiParameter): string {
  return `${parameter.in}:${parameter.name}`
}

function valuesForParameter(
  document: OpenApiDocument,
  parameter: OpenApiParameter,
  value: string,
): string[] {
  const schema = resolveInputSchema(document, parameter.schema)
  if (schema?.type !== "array") {
    return [value]
  }
  return value
    .split(/[\n,]/)
    .map((part) => part.trim())
    .filter(Boolean)
}

function allowsNull(
  document: OpenApiDocument,
  schemaOrReference: OpenApiSchema | OpenApiReference | undefined,
): boolean {
  if (!schemaOrReference) return false
  const schema = "$ref" in schemaOrReference
    ? resolveInputSchema(document, schemaOrReference)
    : schemaOrReference
  if (schema?.nullable || schema?.type === "null") return true
  return [...(schema?.anyOf ?? []), ...(schema?.oneOf ?? [])].some((item) => {
    const resolved = resolveInputSchema(document, item)
    return resolved?.type === "null"
  })
}

function validateJsonValue(
  document: OpenApiDocument,
  schemaOrReference: OpenApiSchema | OpenApiReference | undefined,
  value: unknown,
  path: string,
): void {
  if (value === null && allowsNull(document, schemaOrReference)) return
  const schema = resolveInputSchema(document, schemaOrReference)
  if (!schema) return

  if (schema.type === "object") {
    if (!value || typeof value !== "object" || Array.isArray(value)) {
      throw new Error(`${path} must be a JSON object.`)
    }
    const record = value as Record<string, unknown>
    for (const requiredName of schema.required ?? []) {
      if (
        !(requiredName in record) ||
        record[requiredName] === undefined ||
        record[requiredName] === null ||
        record[requiredName] === ""
      ) {
        throw new Error(`${path}.${requiredName} is required.`)
      }
    }
    for (const [name, propertySchema] of Object.entries(schema.properties ?? {})) {
      if (record[name] !== undefined) {
        validateJsonValue(document, propertySchema, record[name], `${path}.${name}`)
      }
    }
    return
  }

  if (schema.type === "array") {
    if (!Array.isArray(value)) throw new Error(`${path} must be a list.`)
    if (schema.minItems !== undefined && value.length < schema.minItems) {
      throw new Error(`${path} must contain at least ${schema.minItems} item(s).`)
    }
    if (schema.maxItems !== undefined && value.length > schema.maxItems) {
      throw new Error(`${path} must contain at most ${schema.maxItems} item(s).`)
    }
    value.forEach((item, index) =>
      validateJsonValue(document, schema.items, item, `${path}[${index}]`),
    )
    return
  }

  if (schema.type === "string") {
    if (typeof value !== "string") throw new Error(`${path} must be a string.`)
    if (schema.minLength !== undefined && value.length < schema.minLength) {
      throw new Error(`${path} must contain at least ${schema.minLength} characters.`)
    }
    if (schema.maxLength !== undefined && value.length > schema.maxLength) {
      throw new Error(`${path} must contain at most ${schema.maxLength} characters.`)
    }
    if (schema.pattern && !new RegExp(schema.pattern).test(value)) {
      throw new Error(`${path} is not in the expected format.`)
    }
  }
  if (schema.type === "boolean" && typeof value !== "boolean") {
    throw new Error(`${path} must be true or false.`)
  }
  if (
    (schema.type === "integer" || schema.type === "number") &&
    (typeof value !== "number" || !Number.isFinite(value))
  ) {
    throw new Error(`${path} must be a number.`)
  }
  if (schema.type === "integer" && typeof value === "number" && !Number.isInteger(value)) {
    throw new Error(`${path} must be a whole number.`)
  }
  if (
    (schema.type === "integer" || schema.type === "number") &&
    typeof value === "number"
  ) {
    if (schema.minimum !== undefined && value < schema.minimum) {
      throw new Error(`${path} must be at least ${schema.minimum}.`)
    }
    if (schema.maximum !== undefined && value > schema.maximum) {
      throw new Error(`${path} must be at most ${schema.maximum}.`)
    }
  }
  if (
    schema.enum?.length &&
    !schema.enum.some((candidate) => candidate === value)
  ) {
    throw new Error(`${path} must be one of: ${schema.enum.join(", ")}.`)
  }
}

function shellQuote(value: string): string {
  return `'${value.split("'").join("'\\''")}'`
}

function validateParameterValue(
  document: OpenApiDocument,
  parameter: OpenApiParameter,
  value: string,
): void {
  const parameterSchema = resolveInputSchema(document, parameter.schema)
  const schema =
    parameterSchema?.type === "array"
      ? resolveInputSchema(document, parameterSchema.items)
      : parameterSchema
  if (!schema) return

  if (schema.enum?.length && !schema.enum.some((candidate) => String(candidate) === value)) {
    throw new Error(`${parameter.name} must be one of: ${schema.enum.join(", ")}.`)
  }
  if (schema.type === "boolean" && value !== "true" && value !== "false") {
    throw new Error(`${parameter.name} must be true or false.`)
  }
  if (schema.type === "integer" && !/^-?\d+$/.test(value)) {
    throw new Error(`${parameter.name} must be a whole number.`)
  }
  if (schema.type === "number" && !Number.isFinite(Number(value))) {
    throw new Error(`${parameter.name} must be a number.`)
  }
  if (schema.type === "integer" || schema.type === "number") {
    const numericValue = Number(value)
    if (schema.minimum !== undefined && numericValue < schema.minimum) {
      throw new Error(`${parameter.name} must be at least ${schema.minimum}.`)
    }
    if (schema.maximum !== undefined && numericValue > schema.maximum) {
      throw new Error(`${parameter.name} must be at most ${schema.maximum}.`)
    }
  }
  if (
    schema.format === "date" ||
    parameter.name === "pub_date_from" ||
    parameter.name === "pub_date_to"
  ) {
    const parsed = new Date(`${value}T00:00:00Z`)
    if (
      !/^\d{4}-\d{2}-\d{2}$/.test(value) ||
      Number.isNaN(parsed.getTime()) ||
      parsed.toISOString().slice(0, 10) !== value
    ) {
      throw new Error(`${parameter.name} must be a valid date in YYYY-MM-DD format.`)
    }
  }
  if (schema.minLength !== undefined && value.length < schema.minLength) {
    throw new Error(`${parameter.name} must contain at least ${schema.minLength} characters.`)
  }
  if (schema.maxLength !== undefined && value.length > schema.maxLength) {
    throw new Error(`${parameter.name} must contain at most ${schema.maxLength} characters.`)
  }
  if (schema.pattern && !new RegExp(schema.pattern).test(value)) {
    throw new Error(`${parameter.name} is not in the expected format.`)
  }
}

function validateCrossFieldParameters(
  operation: PlaygroundOperation,
  values: ParameterValues,
): void {
  if (!operation.displayPath.endsWith("/geo-search")) return
  const longitude = values["query:center_lng"]?.trim() ?? ""
  const latitude = values["query:center_lat"]?.trim() ?? ""
  const radius = values["query:radius_miles"]?.trim() ?? ""
  const bbox = values["query:bbox"]?.trim() ?? ""
  const pointValues = [longitude, latitude, radius]
  const hasPointValue = pointValues.some(Boolean)
  const hasCompletePoint = pointValues.every(Boolean)
  if (hasPointValue && !hasCompletePoint) {
    throw new Error(
      "center_lng, center_lat, and radius_miles must be provided together.",
    )
  }
  if (hasCompletePoint && bbox) {
    throw new Error("Choose either point and radius fields or bbox, not both.")
  }
  if (!hasCompletePoint && !bbox) {
    throw new Error("Provide point and radius fields or a bbox.")
  }
}

export function prepareRequest(
  document: OpenApiDocument,
  operation: PlaygroundOperation,
  origin: string,
  values: ParameterValues,
  bodyText: string,
  apiKey: string,
): PreparedRequest {
  let path = operation.path
  const query = new URLSearchParams()
  const headers = new Headers({ Accept: "application/json" })
  validateCrossFieldParameters(operation, values)

  for (const parameter of operation.parameters) {
    if (parameter.in === "cookie") {
      continue
    }
    const value = values[parameterKey(parameter)]?.trim() ?? ""
    if (!value) {
      if (parameter.required) {
        throw new Error(`${parameter.name} is required.`)
      }
      continue
    }
    const parsedValues = valuesForParameter(document, parameter, value)
    for (const parsedValue of parsedValues) {
      validateParameterValue(document, parameter, parsedValue)
    }
    if (parameter.in === "path") {
      const pathValue =
        parameter.name === "h3_cell"
          ? (parsedValues[0]
              ?.split(/[\n,]/)
              .map((part) => part.trim())
              .filter(Boolean)[0] ?? "")
          : (parsedValues[0] ?? "")
      if (parameter.name === "h3_cell") {
        const cellCount = (values[parameterKey(parameter)] ?? "")
          .split(/[\n,]/)
          .map((part) => part.trim())
          .filter(Boolean).length
        if (cellCount > 1) {
          throw new Error(
            "This endpoint accepts one h3_cell. Clear the selection to a single cell, or use Batch query for multiple cells.",
          )
        }
      }
      path = path.replace(`{${parameter.name}}`, encodeURIComponent(pathValue))
    } else if (parameter.in === "query") {
      for (const parsedValue of parsedValues) {
        query.append(parameter.name, parsedValue)
      }
    } else if (parameter.in === "header") {
      headers.set(parameter.name, parsedValues.join(","))
    }
  }

  const bodySchema = jsonBodySchema(operation)
  let body: string | undefined
  if (bodySchema && bodyText.trim()) {
    let parsedBody: unknown
    try {
      parsedBody = JSON.parse(bodyText)
    } catch {
      throw new Error("Request body must be valid JSON.")
    }
    validateJsonValue(document, bodySchema, parsedBody, "Request body")
    body = bodyText
    headers.set("Content-Type", "application/json")
  } else if (operation.requestBody?.required && bodySchema) {
    throw new Error("A JSON request body is required.")
  }

  if (apiKey) {
    headers.set("Authorization", `Bearer ${apiKey}`)
  }

  const queryString = query.toString()
  const url = `${origin}${path}${queryString ? `?${queryString}` : ""}`
  const curlParts = ["curl", "-i", "-X", operation.method.toUpperCase(), shellQuote(url)]
  headers.forEach((value, name) => {
    const curlValue =
      name.toLowerCase() === "authorization"
        ? "Authorization: Bearer $BACKFIELD_PROJECT_API_KEY"
        : `${name}: ${value}`
    curlParts.push("-H", shellQuote(curlValue))
  })
  if (body !== undefined) {
    curlParts.push("--data-raw", shellQuote(body))
  }

  return {
    url,
    init: {
      method: operation.method.toUpperCase(),
      headers,
      body,
      credentials: "omit",
      referrerPolicy: "no-referrer",
    },
    curl: curlParts.join(" "),
  }
}

function formatResponseBody(rawBody: string, contentType: string | null): string {
  if (!rawBody || !contentType?.includes("json")) {
    return rawBody
  }
  try {
    return JSON.stringify(JSON.parse(rawBody), null, 2)
  } catch {
    return rawBody
  }
}

export async function executePreparedRequest(request: PreparedRequest): Promise<PlaygroundResponse> {
  const response = await fetch(request.url, request.init)
  const rawBody = await response.text()
  return {
    status: response.status,
    statusText: response.statusText,
    headers: Array.from(response.headers.entries()),
    body: formatResponseBody(rawBody, response.headers.get("content-type")),
    requestId: response.headers.get("x-request-id") ?? undefined,
  }
}

export function keyForParameter(parameter: OpenApiParameter): string {
  return parameterKey(parameter)
}
