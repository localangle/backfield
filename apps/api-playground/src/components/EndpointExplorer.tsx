import { useMemo, useState } from "react"

import {
  exampleForSchema,
  jsonBodySchema,
  resolveSchema,
  type OpenApiDocument,
  type OpenApiParameter,
  type PlaygroundOperation,
} from "../lib/openapi"
import {
  executePreparedRequest,
  keyForParameter,
  prepareRequest,
  type ParameterValues,
  type PlaygroundResponse,
} from "../lib/request"

interface EndpointExplorerProps {
  document: OpenApiDocument
  operation: PlaygroundOperation
  origin: string
  apiKey: string
}

function schemaType(document: OpenApiDocument, parameter: OpenApiParameter): string {
  const schema = resolveSchema(document, parameter.schema)
  if (!schema) {
    return "string"
  }
  if (schema.type === "array") {
    return `array of ${resolveSchema(document, schema.items)?.type ?? "values"}`
  }
  return schema.format ? `${schema.type ?? "value"} (${schema.format})` : (schema.type ?? "value")
}

function ParameterInput({
  document,
  parameter,
  value,
  onChange,
}: {
  document: OpenApiDocument
  parameter: OpenApiParameter
  value: string
  onChange: (value: string) => void
}) {
  const schema = resolveSchema(document, parameter.schema)
  const id = `parameter-${parameter.in}-${parameter.name}`
  const isArray = schema?.type === "array"
  const sharedProps = {
    id,
    value,
    required: parameter.required,
    onChange: (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
      onChange(event.target.value),
    placeholder: isArray ? "One value per line or comma-separated" : undefined,
  }

  return (
    <div className="field">
      <label htmlFor={id}>
        <span className="field-name">{parameter.name}</span>
        <span className="field-meta">
          {parameter.in} · {schemaType(document, parameter)}
          {parameter.required ? " · required" : ""}
        </span>
      </label>
      {parameter.description && <p className="field-description">{parameter.description}</p>}
      {isArray ? <textarea {...sharedProps} rows={3} /> : <input {...sharedProps} type="text" />}
    </div>
  )
}

export default function EndpointExplorer({
  document,
  operation,
  origin,
  apiKey,
}: EndpointExplorerProps) {
  const bodySchema = jsonBodySchema(operation)
  const initialBody = useMemo(() => {
    if (!bodySchema) {
      return ""
    }
    return JSON.stringify(exampleForSchema(document, bodySchema) ?? {}, null, 2)
  }, [bodySchema, document])
  const [values, setValues] = useState<ParameterValues>({})
  const [bodyText, setBodyText] = useState(initialBody)
  const [response, setResponse] = useState<PlaygroundResponse>()
  const [curl, setCurl] = useState("")
  const [error, setError] = useState("")
  const [executing, setExecuting] = useState(false)

  async function execute() {
    setError("")
    setResponse(undefined)
    try {
      const request = prepareRequest(document, operation, origin, values, bodyText, apiKey)
      setCurl(request.curl)
      setExecuting(true)
      setResponse(await executePreparedRequest(request))
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The request failed.")
    } finally {
      setExecuting(false)
    }
  }

  const supportedParameters = operation.parameters.filter(
    (parameter) => parameter.in !== "cookie",
  )

  return (
    <section
      className="operation-panel"
      aria-labelledby="operation-title"
      aria-busy={executing}
    >
      <header className="operation-header">
        <span className={`method method-${operation.method}`}>{operation.method.toUpperCase()}</span>
        <div>
          <code className="operation-path">{operation.path}</code>
          <h2 id="operation-title">{operation.summary}</h2>
        </div>
      </header>
      {operation.description && <p className="operation-description">{operation.description}</p>}

      {supportedParameters.length > 0 && (
        <fieldset>
          <legend>Parameters</legend>
          <div className="fields-grid">
            {supportedParameters.map((parameter) => {
              const key = keyForParameter(parameter)
              return (
                <ParameterInput
                  key={key}
                  document={document}
                  parameter={parameter}
                  value={values[key] ?? ""}
                  onChange={(value) => setValues((current) => ({ ...current, [key]: value }))}
                />
              )
            })}
          </div>
        </fieldset>
      )}

      {bodySchema && (
        <div className="field body-field">
          <label htmlFor="request-body">
            <span className="field-name">JSON request body</span>
            <span className="field-meta">
              application/json{operation.requestBody?.required ? " · required" : ""}
            </span>
          </label>
          {operation.requestBody?.description && (
            <p className="field-description">{operation.requestBody.description}</p>
          )}
          <textarea
            id="request-body"
            className="code-input"
            rows={12}
            value={bodyText}
            onChange={(event) => setBodyText(event.target.value)}
            spellCheck={false}
          />
        </div>
      )}

      <button
        className="execute-button"
        type="button"
        disabled={executing}
        aria-describedby={error ? "request-error" : undefined}
        onClick={execute}
      >
        {executing ? "Sending request…" : "Execute request"}
      </button>
      {error && (
        <p id="request-error" className="error-message" role="alert">
          {error}
        </p>
      )}

      {curl && (
        <section className="result-block" aria-labelledby="curl-title">
          <h3 id="curl-title">Generated curl</h3>
          <p className="result-note">
            The API key is represented by an environment variable and is not copied into this
            command.
          </p>
          <pre>{curl}</pre>
        </section>
      )}

      {response && (
        <section
          className="response-section"
          aria-labelledby="response-title"
          aria-live="polite"
        >
          <div className="response-heading">
            <h3 id="response-title">Response</h3>
            <span className={`status ${response.status < 400 ? "status-ok" : "status-error"}`}>
              {response.status} {response.statusText}
            </span>
          </div>
          <dl className="response-metadata">
            <div>
              <dt>Request ID</dt>
              <dd>{response.requestId ?? "Not returned"}</dd>
            </div>
          </dl>
          <div className="result-block">
            <h4>Headers</h4>
            <pre>
              {response.headers.map(([name, value]) => `${name}: ${value}`).join("\n") ||
                "No response headers exposed"}
            </pre>
          </div>
          <div className="result-block">
            <h4>Body</h4>
            <pre>{response.body || "Empty response body"}</pre>
          </div>
        </section>
      )}
    </section>
  )
}
