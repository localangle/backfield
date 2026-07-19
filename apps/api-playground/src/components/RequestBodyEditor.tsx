import { lazy, Suspense, useMemo, useState } from "react"

import ParameterField from "./ParameterField"
import {
  resolveInputSchema,
  type OpenApiDocument,
  type OpenApiSchema,
  type PlaygroundOperation,
} from "../lib/openapi"
import {
  presentationForField,
  sectionsForBodyFields,
  type PresentationContext,
} from "../lib/presentation"

const H3CellMap = lazy(() => import("./H3CellMap"))

interface RequestBodyEditorProps {
  apiKey: string
  bodyText: string
  context: PresentationContext
  document: OpenApiDocument
  operation: PlaygroundOperation
  origin: string
  projectSlug: string
  schema: OpenApiSchema
  onChange: (bodyText: string) => void
}

function parseBody(bodyText: string): Record<string, unknown> {
  try {
    const parsed = JSON.parse(bodyText) as unknown
    return parsed && typeof parsed === "object" && !Array.isArray(parsed)
      ? (parsed as Record<string, unknown>)
      : {}
  } catch {
    return {}
  }
}

function valueForField(value: unknown, schema: OpenApiSchema | undefined): string {
  if (value === undefined || value === null) return ""
  if (schema?.type === "array" && Array.isArray(value)) {
    return value.map(String).join("\n")
  }
  if (schema?.type === "object") return JSON.stringify(value, null, 2)
  return String(value)
}

function valueForJson(value: string, schema: OpenApiSchema | undefined): unknown {
  const trimmed = value.trim()
  if (!trimmed) return undefined
  if (schema?.type === "array") {
    return trimmed
      .split(/[\n,]/)
      .map((item) => item.trim())
      .filter(Boolean)
  }
  if (schema?.type === "boolean") return trimmed === "true"
  if (schema?.type === "integer" || schema?.type === "number") return Number(trimmed)
  if (schema?.type === "object") {
    try {
      return JSON.parse(trimmed)
    } catch {
      return trimmed
    }
  }
  return value
}

export default function RequestBodyEditor({
  apiKey,
  bodyText,
  context,
  document,
  operation,
  origin,
  projectSlug,
  schema,
  onChange,
}: RequestBodyEditorProps) {
  const [rawMode, setRawMode] = useState(false)
  const properties = schema.properties ?? {}
  const names = Object.keys(properties)
  const requiredNames = new Set(schema.required ?? [])
  const body = useMemo(() => parseBody(bodyText), [bodyText])

  function setField(name: string, value: string, fieldSchema: OpenApiSchema | undefined) {
    const next = { ...body }
    const parsedValue = valueForJson(value, fieldSchema)
    if (parsedValue === undefined) delete next[name]
    else next[name] = parsedValue
    onChange(JSON.stringify(next, null, 2))
  }

  function setFields(changes: Record<string, unknown>) {
    const next = { ...body }
    for (const [name, value] of Object.entries(changes)) {
      if (
        value === undefined ||
        value === null ||
        (Array.isArray(value) && value.length === 0)
      ) {
        delete next[name]
      } else {
        next[name] = value
      }
    }
    onChange(JSON.stringify(next, null, 2))
  }

  return (
    <div className="body-field">
      <div className="body-editor-heading">
        <div>
          <span className="field-name">
            Request body
            {operation.requestBody?.required && (
              <span className="required-mark" aria-hidden>
                *
              </span>
            )}
          </span>
          <span className="field-meta">
            application/json
            {operation.requestBody?.required && (
              <span className="required-badge">Required</span>
            )}
          </span>
        </div>
        <button
          type="button"
          className="secondary-button body-mode-toggle"
          onClick={() => setRawMode((current) => !current)}
        >
          {rawMode ? "Use form" : "Edit as JSON"}
        </button>
      </div>
      {operation.requestBody?.description && (
        <p className="field-description">{operation.requestBody.description}</p>
      )}

      {rawMode ? (
        <textarea
          id="request-body"
          aria-label="JSON request body"
          className="code-input"
          rows={12}
          value={bodyText}
          onChange={(event) => onChange(event.target.value)}
          spellCheck={false}
        />
      ) : (
        <div className="parameter-sections body-parameter-sections">
          {sectionsForBodyFields(names).map((section) => (
            <section
              className="parameter-section"
              key={section.id}
              aria-labelledby={`request-${section.id}`}
            >
              <div className="parameter-section-heading">
                <h3 id={`request-${section.id}`}>{section.title}</h3>
                <p>{section.description}</p>
              </div>
              {section.names.includes("cells") && section.names.includes("resolution") && (
                <Suspense
                  fallback={<div className="map-selector-loading">Loading map…</div>}
                >
                  <H3CellMap
                    cells={Array.isArray(body.cells) ? body.cells.map(String) : []}
                    resolution={
                      typeof body.resolution === "number" ? body.resolution : 6
                    }
                    onChange={(cells, resolution) =>
                      setFields({ cells, resolution })
                    }
                  />
                </Suspense>
              )}
              <div className="fields-grid parameter-fields-grid">
                {section.names.map((name) => {
                  const fieldSchema = resolveInputSchema(document, properties[name])
                  const presentation = presentationForField(
                    operation,
                    name,
                    fieldSchema,
                    fieldSchema?.description,
                    context,
                    "body",
                  )
                  return (
                    <ParameterField
                      key={name}
                      id={`body-${name}`}
                      name={name}
                      schema={fieldSchema}
                      presentation={presentation}
                      required={requiredNames.has(name)}
                      value={valueForField(body[name], fieldSchema)}
                      wide={section.wide.has(name)}
                      origin={origin}
                      projectSlug={projectSlug}
                      apiKey={apiKey}
                      onChange={(value) => setField(name, value, fieldSchema)}
                    />
                  )
                })}
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  )
}
