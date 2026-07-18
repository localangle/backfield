import { useMemo, useState } from "react"

import {
  exampleForSchema,
  jsonBodySchema,
  resolveInputSchema,
  type OpenApiDocument,
  type OpenApiParameter,
  type OpenApiSchema,
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

interface SelectOption {
  value: string
  label: string
}

interface ParameterPresentation {
  control: "date" | "number" | "select" | "text" | "textarea"
  description?: string
  emptyLabel?: string
  options?: SelectOption[]
  placeholder?: string
  typeLabel: string
}

interface ParameterSection {
  title: string
  description: string
  names: string[]
  wide: Set<string>
}

const articleSearchSections: ParameterSection[] = [
  {
    title: "Project",
    description: "Choose the project whose articles you want to search.",
    names: ["project_slug"],
    wide: new Set(["project_slug"]),
  },
  {
    title: "Search and filters",
    description: "Add only the filters you need. Empty optional fields are not sent.",
    names: [
      "q",
      "author",
      "external_source",
      "has_mentions",
      "pub_date_from",
      "pub_date_to",
      "meta",
    ],
    wide: new Set(["q", "has_mentions", "meta"]),
  },
  {
    title: "Sort and page",
    description: "Control result order and pagination.",
    names: ["sort", "sort_direction", "limit", "offset"],
    wide: new Set(),
  },
  {
    title: "Response details",
    description: "Optionally include additional computed fields in each result.",
    names: ["include"],
    wide: new Set(["include"]),
  },
]

const articleSearchDescriptions: Record<string, string> = {
  pub_date_from: "Include articles published on or after this date.",
  pub_date_to: "Include articles published on or before this date.",
  limit: "Number of results to return. The default is 25; the maximum is 100.",
  offset: "Number of results to skip. The default is 0.",
}

function enumOptions(schema: OpenApiSchema | undefined): SelectOption[] | undefined {
  if (!schema?.enum?.length) return undefined
  return schema.enum.map((value) => ({ value: String(value), label: String(value) }))
}

function parameterPresentation(
  operation: PlaygroundOperation,
  parameter: OpenApiParameter,
  schema: OpenApiSchema | undefined,
): ParameterPresentation {
  const isArticleSearch = operation.displayPath === "/articles/search"
  if (isArticleSearch) {
    if (parameter.name === "q") {
      return {
        control: "text",
        description: parameter.description,
        placeholder: 'For example: budget OR "city council"',
        typeLabel: "String",
      }
    }
    if (parameter.name === "has_mentions") {
      return {
        control: "select",
        description: "Require at least one mention of a specific entity type.",
        emptyLabel: "Any mention type",
        options: [
          { value: "location", label: "Location" },
          { value: "person", label: "Person" },
          { value: "organization", label: "Organization" },
        ],
        typeLabel: "String",
      }
    }
    if (parameter.name === "pub_date_from" || parameter.name === "pub_date_to") {
      return {
        control: "date",
        description: articleSearchDescriptions[parameter.name],
        typeLabel: "Date",
      }
    }
    if (parameter.name === "include") {
      return {
        control: "select",
        description: parameter.description,
        emptyLabel: "No extra details",
        options: [{ value: "counts", label: "Counts" }],
        typeLabel: "String",
      }
    }
    if (parameter.name === "sort") {
      return {
        control: "select",
        description: parameter.description,
        emptyLabel: "Automatic: relevance with keywords; otherwise publication date",
        options: [
          { value: "relevance", label: "Relevance" },
          { value: "pub_date", label: "Publication date" },
        ],
        typeLabel: "String",
      }
    }
    if (parameter.name === "sort_direction") {
      return {
        control: "select",
        description: parameter.description,
        emptyLabel: "Default: descending",
        options: [
          { value: "asc", label: "Ascending" },
          { value: "desc", label: "Descending" },
        ],
        typeLabel: "String",
      }
    }
    if (parameter.name === "meta") {
      return {
        control: "textarea",
        description: parameter.description,
        placeholder: "One clause per line, for example:\ntopic:politics\n!format:opinion",
        typeLabel: "Repeatable string",
      }
    }
  }

  const options = enumOptions(schema)
  if (options) {
    return {
      control: "select",
      description: parameter.description,
      options,
      typeLabel: schema?.type === "integer" ? "Integer" : "String",
    }
  }
  if (schema?.type === "boolean") {
    return {
      control: "select",
      description: parameter.description,
      options: [
        { value: "true", label: "True" },
        { value: "false", label: "False" },
      ],
      typeLabel: "Boolean",
    }
  }
  if (schema?.type === "array") {
    return {
      control: "textarea",
      description: parameter.description,
      placeholder: "One value per line or comma-separated",
      typeLabel: "Repeatable string",
    }
  }
  if (schema?.type === "integer" || schema?.type === "number") {
    return {
      control: "number",
      description: articleSearchDescriptions[parameter.name] ?? parameter.description,
      placeholder:
        schema.default !== undefined ? `Default: ${String(schema.default)}` : undefined,
      typeLabel: schema.type === "integer" ? "Integer" : "Number",
    }
  }
  return {
    control: schema?.format === "date" ? "date" : "text",
    description: parameter.description,
    typeLabel: schema?.format === "date" ? "Date" : "String",
  }
}

function ParameterInput({
  document,
  operation,
  parameter,
  value,
  wide,
  onChange,
}: {
  document: OpenApiDocument
  operation: PlaygroundOperation
  parameter: OpenApiParameter
  value: string
  wide?: boolean
  onChange: (value: string) => void
}) {
  const schema = resolveInputSchema(document, parameter.schema)
  const presentation = parameterPresentation(operation, parameter, schema)
  const id = `parameter-${parameter.in}-${parameter.name}`
  const descriptionId = `${id}-description`
  const defaultLabel =
    schema?.default !== undefined &&
    !(Array.isArray(schema.default) && schema.default.length === 0)
      ? `Default: ${String(schema.default)}`
      : undefined
  const helpText = presentation.description ?? defaultLabel
  const describedBy = helpText ? descriptionId : undefined

  return (
    <div className={`field parameter-field ${wide ? "parameter-field-wide" : ""}`}>
      <label htmlFor={id}>
        <span className="field-name">{parameter.name}</span>
        <span className="field-meta">
          {presentation.typeLabel}
          {parameter.required ? " · required" : ""}
        </span>
      </label>
      <div className="parameter-description-slot">
        {helpText && (
          <p id={descriptionId} className="field-description">
            {helpText}
          </p>
        )}
      </div>
      {presentation.control === "select" ? (
        <select
          id={id}
          value={value}
          required={parameter.required}
          aria-describedby={describedBy}
          onChange={(event) => onChange(event.target.value)}
        >
          <option value="">
            {parameter.required
              ? "Select a value"
              : presentation.emptyLabel ?? defaultLabel ?? "Any"}
          </option>
          {presentation.options?.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      ) : presentation.control === "textarea" ? (
        <textarea
          id={id}
          value={value}
          required={parameter.required}
          aria-describedby={describedBy}
          onChange={(event) => onChange(event.target.value)}
          placeholder={presentation.placeholder}
          rows={parameter.name === "meta" ? 4 : 3}
        />
      ) : (
        <input
          id={id}
          value={value}
          required={parameter.required}
          aria-describedby={describedBy}
          onChange={(event) => onChange(event.target.value)}
          placeholder={presentation.placeholder}
          type={presentation.control}
          min={schema?.minimum}
          max={schema?.maximum}
          minLength={schema?.minLength}
          maxLength={schema?.maxLength}
          pattern={schema?.pattern}
          step={schema?.type === "integer" ? 1 : undefined}
        />
      )}
    </div>
  )
}

function sectionsForOperation(
  operation: PlaygroundOperation,
  parameters: OpenApiParameter[],
): ParameterSection[] {
  if (operation.displayPath !== "/articles/search") {
    return [
      {
        title: "",
        description: "",
        names: parameters.map((parameter) => parameter.name),
        wide: new Set(),
      },
    ]
  }
  const namedParameters = new Set(
    articleSearchSections.flatMap((section) => section.names),
  )
  const additionalParameters = parameters
    .map((parameter) => parameter.name)
    .filter((name) => !namedParameters.has(name))
  return additionalParameters.length
    ? [
        ...articleSearchSections,
        {
          title: "Other parameters",
          description: "Additional options provided by the current API schema.",
          names: additionalParameters,
          wide: new Set<string>(),
        },
      ]
    : articleSearchSections
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
          <code className="operation-path" title={operation.path}>
            {operation.displayPath}
          </code>
          <h2 id="operation-title">{operation.summary}</h2>
        </div>
      </header>
      {operation.description && <p className="operation-description">{operation.description}</p>}

      {supportedParameters.length > 0 && (
        <fieldset className="parameters-panel">
          <legend>Parameters</legend>
          <div className="parameter-sections">
            {sectionsForOperation(operation, supportedParameters).map((section) => {
              const sectionParameters = section.names
                .map((name) => supportedParameters.find((parameter) => parameter.name === name))
                .filter((parameter): parameter is OpenApiParameter => parameter !== undefined)
              if (!sectionParameters.length) return null
              const sectionId = section.title
                ? `parameter-section-${section.title.toLowerCase().replace(/\s+/g, "-")}`
                : undefined
              return (
                <section
                  className="parameter-section"
                  key={section.title || "parameters"}
                  aria-labelledby={sectionId}
                >
                  {section.title && (
                    <div className="parameter-section-heading">
                      <h3 id={sectionId}>{section.title}</h3>
                      <p>{section.description}</p>
                    </div>
                  )}
                  <div className="fields-grid parameter-fields-grid">
                    {sectionParameters.map((parameter) => {
                      const key = keyForParameter(parameter)
                      return (
                        <ParameterInput
                          key={key}
                          document={document}
                          operation={operation}
                          parameter={parameter}
                          value={values[key] ?? ""}
                          wide={section.wide.has(parameter.name)}
                          onChange={(value) =>
                            setValues((current) => ({ ...current, [key]: value }))
                          }
                        />
                      )
                    })}
                  </div>
                </section>
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
