import { lazy, Suspense, useEffect, useMemo, useState } from "react"
import { Check, Copy } from "lucide-react"

import {
  fetchArticleFacets,
  fetchArticleMetaTypes,
  fetchMentionFacets,
} from "../lib/api"
import ParameterField from "./ParameterField"
import RequestBodyEditor from "./RequestBodyEditor"
import {
  exampleForSchema,
  jsonBodySchema,
  listOperations,
  resolveInputSchema,
  type OpenApiDocument,
  type OpenApiParameter,
  type PlaygroundOperation,
} from "../lib/openapi"
import {
  operationNeedsArticleFacets,
  operationNeedsMentionFacets,
  operationNeedsMetadataTypes,
  presentationForField,
  sectionsForOperation,
  type OptionLoad,
  type PresentationContext,
  type SelectOption,
} from "../lib/presentation"
import {
  executePreparedRequest,
  keyForParameter,
  prepareRequest,
  type ParameterValues,
  type PlaygroundResponse,
} from "../lib/request"
import { cellResolution } from "../lib/mapSelection"

const GeoAreaMap = lazy(() => import("./GeoAreaMap"))
const H3CellMap = lazy(() => import("./H3CellMap"))

function MapLoading() {
  return <div className="map-selector-loading">Loading map…</div>
}

interface EndpointExplorerProps {
  document: OpenApiDocument
  operation: PlaygroundOperation
  origin: string
  apiKey: string
  projectOptions?: SelectOption[]
  projectSlug?: string
  onProjectSlugChange?: (projectSlug: string) => void
}

interface ProjectOptionLoad extends OptionLoad {
  projectSlug: string
}

function CopyButton({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false)

  async function copy() {
    try {
      await navigator.clipboard.writeText(value)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1600)
    } catch {
      setCopied(false)
    }
  }

  return (
    <button
      type="button"
      className="copy-button"
      aria-label={copied ? `${label} copied` : label}
      title={copied ? "Copied" : label}
      onClick={() => void copy()}
    >
      {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
    </button>
  )
}

function ParameterInput({
  document,
  operation,
  parameter,
  presentationContext,
  entityType,
  selectedProjectSlug,
  origin,
  apiKey,
  value,
  wide,
  onChange,
}: {
  document: OpenApiDocument
  operation: PlaygroundOperation
  parameter: OpenApiParameter
  presentationContext: PresentationContext
  entityType?: string
  selectedProjectSlug: string
  origin: string
  apiKey: string
  value: string
  wide?: boolean
  onChange: (value: string) => void
}) {
  const schema = resolveInputSchema(document, parameter.schema)
  const presentation = presentationForField(
    operation,
    parameter.name,
    schema,
    parameter.description,
    presentationContext,
    parameter.in,
  )
  const id = `parameter-${parameter.in}-${parameter.name}`

  return (
    <ParameterField
      id={id}
      name={parameter.name}
      schema={schema}
      presentation={presentation}
      entityType={entityType}
      required={parameter.required}
      value={value}
      wide={wide}
      origin={origin}
      projectSlug={selectedProjectSlug}
      apiKey={apiKey}
      onChange={onChange}
    />
  )
}

export default function EndpointExplorer({
  document,
  operation,
  origin,
  apiKey,
  projectOptions = [],
  projectSlug = "",
  onProjectSlugChange,
}: EndpointExplorerProps) {
  const bodySchema = jsonBodySchema(operation)
  const resolvedBodySchema = resolveInputSchema(document, bodySchema)
  const initialBody = useMemo(() => {
    if (!bodySchema) {
      return ""
    }
    return JSON.stringify(exampleForSchema(document, bodySchema) ?? {}, null, 2)
  }, [bodySchema, document])
  const [values, setValues] = useState<ParameterValues>(() => {
    const initialValues: ParameterValues = {}
    if (
      operation.parameters.some(
      (parameter) => parameter.in === "path" && parameter.name === "project_slug",
      ) &&
      projectSlug
    ) {
      initialValues["path:project_slug"] = projectSlug
    }
    return initialValues
  })
  const selectedProjectSlug = values["path:project_slug"] ?? ""
  const [articleFacetLoad, setArticleFacetLoad] = useState<ProjectOptionLoad>({
    projectSlug: "",
    status: "blocked",
    values: {},
  })
  const [mentionFacetLoad, setMentionFacetLoad] = useState<ProjectOptionLoad>({
    projectSlug: "",
    status: "blocked",
    values: {},
  })
  const [metadataTypeLoad, setMetadataTypeLoad] = useState<ProjectOptionLoad>({
    projectSlug: "",
    status: "blocked",
    values: {},
  })
  const [bodyText, setBodyText] = useState(initialBody)
  const [response, setResponse] = useState<PlaygroundResponse>()
  const [curl, setCurl] = useState("")
  const [error, setError] = useState("")
  const [executing, setExecuting] = useState(false)
  const [h3HighlightCells, setH3HighlightCells] = useState<string[]>([])
  const bodyFieldNames = new Set(Object.keys(resolvedBodySchema?.properties ?? {}))
  const needsArticleFacets =
    operationNeedsArticleFacets(operation) ||
    bodyFieldNames.has("author") ||
    bodyFieldNames.has("external_source")
  const needsMentionFacets =
    operationNeedsMentionFacets(operation) ||
    ["nature", "location_type", "person_type", "organization_type"].some((name) =>
      bodyFieldNames.has(name),
    )

  useEffect(() => {
    if (!needsArticleFacets || !selectedProjectSlug || !apiKey) {
      setArticleFacetLoad({
        projectSlug: selectedProjectSlug,
        status: "blocked",
        values: {},
      })
      return
    }

    const controller = new AbortController()
    setArticleFacetLoad({
      projectSlug: selectedProjectSlug,
      status: "loading",
      values: {},
    })
    void fetchArticleFacets(
      origin,
      selectedProjectSlug,
      apiKey,
      controller.signal,
    )
      .then((facets) => {
        setArticleFacetLoad({
          projectSlug: selectedProjectSlug,
          status: "ready",
          values: {
            authors: facets.authors,
            externalSources: facets.externalSources,
          },
        })
      })
      .catch((caught: unknown) => {
        if (caught instanceof DOMException && caught.name === "AbortError") return
        setArticleFacetLoad({
          projectSlug: selectedProjectSlug,
          status: "error",
          values: {},
        })
      })
    return () => controller.abort()
  }, [apiKey, needsArticleFacets, origin, selectedProjectSlug])

  useEffect(() => {
    if (!needsMentionFacets || !selectedProjectSlug || !apiKey) {
      setMentionFacetLoad({
        projectSlug: selectedProjectSlug,
        status: "blocked",
        values: {},
      })
      return
    }
    const controller = new AbortController()
    setMentionFacetLoad({
      projectSlug: selectedProjectSlug,
      status: "loading",
      values: {},
    })
    void fetchMentionFacets(origin, selectedProjectSlug, apiKey, controller.signal)
      .then((facets) => {
        setMentionFacetLoad({
          projectSlug: selectedProjectSlug,
          status: "ready",
          values: {
            entityTypes: facets.entityTypes,
            natures: facets.natures,
            locationTypes: facets.locationTypes,
            personTypes: facets.personTypes,
            organizationTypes: facets.organizationTypes,
          },
        })
      })
      .catch((caught: unknown) => {
        if (caught instanceof DOMException && caught.name === "AbortError") return
        setMentionFacetLoad({
          projectSlug: selectedProjectSlug,
          status: "error",
          values: {},
        })
      })
    return () => controller.abort()
  }, [apiKey, needsMentionFacets, origin, selectedProjectSlug])

  useEffect(() => {
    if (!operationNeedsMetadataTypes(operation) || !selectedProjectSlug || !apiKey) {
      setMetadataTypeLoad({
        projectSlug: selectedProjectSlug,
        status: "blocked",
        values: {},
      })
      return
    }
    const controller = new AbortController()
    setMetadataTypeLoad({
      projectSlug: selectedProjectSlug,
      status: "loading",
      values: {},
    })
    void fetchArticleMetaTypes(origin, selectedProjectSlug, apiKey, controller.signal)
      .then((metaTypes) => {
        setMetadataTypeLoad({
          projectSlug: selectedProjectSlug,
          status: "ready",
          values: { metaTypes },
        })
      })
      .catch((caught: unknown) => {
        if (caught instanceof DOMException && caught.name === "AbortError") return
        setMetadataTypeLoad({
          projectSlug: selectedProjectSlug,
          status: "error",
          values: {},
        })
      })
    return () => controller.abort()
  }, [apiKey, operation, origin, selectedProjectSlug])

  useEffect(() => {
    setH3HighlightCells([])
  }, [operation.id, operation.displayPath])

  useEffect(() => {
    setError("")
  }, [bodyText, values])

  const presentationContext: PresentationContext = {
    projectOptions,
    articleFacets: articleFacetLoad,
    mentionFacets: mentionFacetLoad,
    metadataTypes: metadataTypeLoad,
  }

  async function execute() {
    setError("")
    setResponse(undefined)
    try {
      const selectedCells = (
        h3HighlightCells.length > 0
          ? h3HighlightCells
          : (values["path:h3_cell"] ?? "")
              .split(/[\n,]/)
              .map((cell) => cell.trim())
              .filter(Boolean)
      )
      const isSingleCellDetail = /^\/articles\/geo-cells\/\{[^}]+\}$/.test(
        operation.displayPath,
      )

      let request
      if (isSingleCellDetail && selectedCells.length > 1) {
        const batchOperation = listOperations(document).find(
          (candidate) =>
            candidate.method === "post" &&
            candidate.displayPath === "/articles/geo-cells/query",
        )
        if (!batchOperation) {
          throw new Error(
            "Multiple H3 cells are selected, but the batch query endpoint is unavailable.",
          )
        }
        const batchBody: Record<string, unknown> = {
          cells: selectedCells,
          resolution: cellResolution(selectedCells[0]) ?? 6,
        }
        for (const name of [
          "location_type",
          "nature",
          "external_source",
          "pub_date_from",
          "pub_date_to",
        ]) {
          const value = values[`query:${name}`]?.trim()
          if (value) batchBody[name] = value
        }
        const meta = values["query:meta"]?.trim()
        if (meta) {
          batchBody.meta = meta
            .split(/[\n,]/)
            .map((item) => item.trim())
            .filter(Boolean)
        }
        const limit = values["query:limit"]?.trim()
        if (limit) batchBody.limit = Number(limit)
        const offset = values["query:offset"]?.trim()
        if (offset) batchBody.offset = Number(offset)

        request = prepareRequest(
          document,
          batchOperation,
          origin,
          { "path:project_slug": values["path:project_slug"] ?? "" },
          JSON.stringify(batchBody, null, 2),
          apiKey,
        )
      } else {
        const requestValues =
          isSingleCellDetail && selectedCells.length === 1
            ? { ...values, "path:h3_cell": selectedCells[0] }
            : values
        request = prepareRequest(
          document,
          operation,
          origin,
          requestValues,
          bodyText,
          apiKey,
        )
      }
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
            {sectionsForOperation(supportedParameters).map((section) => {
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
                  {sectionParameters.some((parameter) => parameter.name === "bbox") && (
                    <Suspense fallback={<MapLoading />}>
                      <GeoAreaMap
                        key={`${operation.displayPath}-geo-map`}
                        bbox={values["query:bbox"] ?? ""}
                        centerLat={values["query:center_lat"] ?? ""}
                        centerLng={values["query:center_lng"] ?? ""}
                        radiusMiles={values["query:radius_miles"] ?? ""}
                        supportsPoint={operation.displayPath.endsWith("/geo-search")}
                        onChange={(changed) =>
                          setValues((current) => ({
                            ...current,
                            ...(changed.bbox !== undefined
                              ? { "query:bbox": changed.bbox }
                              : {}),
                            ...(changed.centerLat !== undefined
                              ? { "query:center_lat": changed.centerLat }
                              : {}),
                            ...(changed.centerLng !== undefined
                              ? { "query:center_lng": changed.centerLng }
                              : {}),
                            ...(changed.radiusMiles !== undefined
                              ? { "query:radius_miles": changed.radiusMiles }
                              : {}),
                          }))
                        }
                      />
                    </Suspense>
                  )}
                  {sectionParameters.some((parameter) => parameter.name === "h3_cell") && (
                    <Suspense fallback={<MapLoading />}>
                      <H3CellMap
                        key={`${operation.displayPath}-h3-map`}
                        cells={
                          h3HighlightCells.length > 0
                            ? h3HighlightCells
                            : (values["path:h3_cell"] ?? "")
                                .split(/[\n,]/)
                                .map((cell) => cell.trim())
                                .filter(Boolean)
                        }
                        resolution={6}
                        onChange={(cells) => {
                          setH3HighlightCells(cells)
                          setValues((current) => ({
                            ...current,
                            "path:h3_cell": cells.join("\n"),
                          }))
                        }}
                      />
                    </Suspense>
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
                          presentationContext={presentationContext}
                          entityType={
                            values["path:entity_type"] ??
                            values["query:entity_type"]
                          }
                          selectedProjectSlug={selectedProjectSlug}
                          origin={origin}
                          apiKey={apiKey}
                          value={values[key] ?? ""}
                          wide={section.wide.has(parameter.name)}
                          onChange={(value) => {
                            if (
                              parameter.in === "path" &&
                              parameter.name === "project_slug"
                            ) {
                              onProjectSlugChange?.(value)
                              setBodyText(initialBody)
                            }
                            if (
                              parameter.in === "path" &&
                              parameter.name === "h3_cell"
                            ) {
                              setH3HighlightCells(
                                value
                                  .split(/[\n,]/)
                                  .map((cell) => cell.trim())
                                  .filter(Boolean),
                              )
                            }
                            setValues((current) => {
                              const next = { ...current, [key]: value }
                              if (
                                parameter.in === "path" &&
                                parameter.name === "project_slug"
                              ) {
                                delete next["query:author"]
                                delete next["query:external_source"]
                                next["query:meta"] = ""
                                for (const idName of [
                                  "article_id",
                                  "location_id",
                                  "mention_id",
                                  "organization_id",
                                  "person_id",
                                ]) {
                                  delete next[`path:${idName}`]
                                }
                                setH3HighlightCells([])
                              }
                              if (
                                parameter.name === "entity_type" &&
                                (parameter.in === "path" || parameter.in === "query")
                              ) {
                                delete next["path:mention_id"]
                              }
                              return next
                            })
                          }}
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

      {resolvedBodySchema && (
        <RequestBodyEditor
          document={document}
          operation={operation}
          schema={resolvedBodySchema}
          bodyText={bodyText}
          onChange={setBodyText}
          context={presentationContext}
          origin={origin}
          projectSlug={selectedProjectSlug}
          apiKey={apiKey}
        />
      )}

      <button
        className="execute-button"
        type="button"
        disabled={executing || !apiKey}
        aria-describedby={error ? "request-error" : undefined}
        onClick={execute}
      >
        {executing ? "Sending request…" : "Execute request"}
      </button>
      {!apiKey && (
        <p className="result-note">Add a project API key above to execute requests.</p>
      )}
      {error && (
        <p id="request-error" className="error-message" role="alert">
          {error}
        </p>
      )}

      {curl && (
        <section className="result-block" aria-labelledby="curl-title">
          <div className="result-block-heading">
            <h3 id="curl-title">Generated curl</h3>
            <CopyButton label="Copy curl" value={curl} />
          </div>
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
            <div className="result-block-heading">
              <h4>Body</h4>
              <CopyButton label="Copy response body" value={response.body} />
            </div>
            <pre>{response.body || "Empty response body"}</pre>
          </div>
        </section>
      )}
    </section>
  )
}
