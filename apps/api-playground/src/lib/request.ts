import {
  type OpenApiDocument,
  type OpenApiParameter,
  type PlaygroundOperation,
  jsonBodySchema,
  resolveSchema,
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
  const schema = resolveSchema(document, parameter.schema)
  if (schema?.type !== "array") {
    return [value]
  }
  return value
    .split(/[\n,]/)
    .map((part) => part.trim())
    .filter(Boolean)
}

function shellQuote(value: string): string {
  return `'${value.split("'").join("'\\''")}'`
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
    if (parameter.in === "path") {
      path = path.replace(`{${parameter.name}}`, encodeURIComponent(parsedValues[0] ?? ""))
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
    try {
      JSON.parse(bodyText)
    } catch {
      throw new Error("Request body must be valid JSON.")
    }
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
