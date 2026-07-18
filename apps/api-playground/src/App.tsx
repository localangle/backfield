import { useMemo, useState } from "react"

import EndpointExplorer from "./components/EndpointExplorer"
import { fetchPublicSchema } from "./lib/api"
import { listOperations, type OpenApiDocument, type PlaygroundOperation } from "./lib/openapi"
import {
  deriveApiOrigin,
  isLocalPlaygroundHost,
  LOCAL_API_ORIGIN,
  normalizeOrganizationSlug,
  validateOrganizationSlug,
} from "./lib/origin"

interface OperationGroup {
  name: string
  operations: PlaygroundOperation[]
}

function groupOperations(operations: PlaygroundOperation[]): OperationGroup[] {
  const groups = new Map<string, PlaygroundOperation[]>()
  for (const operation of operations) {
    groups.set(operation.group, [...(groups.get(operation.group) ?? []), operation])
  }
  return Array.from(groups, ([name, groupedOperations]) => ({
    name,
    operations: groupedOperations,
  }))
}

export default function App() {
  const localAvailable = isLocalPlaygroundHost(window.location.hostname)
  const [organizationSlug, setOrganizationSlug] = useState("")
  const [useLocalApi, setUseLocalApi] = useState(false)
  const [apiKey, setApiKey] = useState("")
  const [document, setDocument] = useState<OpenApiDocument>()
  const [origin, setOrigin] = useState("")
  const [selectedOperationId, setSelectedOperationId] = useState("")
  const [filter, setFilter] = useState("")
  const [loading, setLoading] = useState(false)
  const [connectionError, setConnectionError] = useState("")

  const operations = useMemo(() => (document ? listOperations(document) : []), [document])
  const visibleGroups = useMemo(() => {
    const query = filter.trim().toLowerCase()
    const visible = query
      ? operations.filter((operation) =>
          [operation.group, operation.method, operation.path, operation.summary]
            .join(" ")
            .toLowerCase()
            .includes(query),
        )
      : operations
    return groupOperations(visible)
  }, [filter, operations])
  const selectedOperation =
    operations.find((operation) => operation.id === selectedOperationId) ?? operations[0]

  async function connect() {
    setConnectionError("")
    let nextOrigin: string
    if (useLocalApi && localAvailable) {
      nextOrigin = LOCAL_API_ORIGIN
    } else {
      const error = validateOrganizationSlug(organizationSlug)
      if (error) {
        setConnectionError(error)
        return
      }
      nextOrigin = deriveApiOrigin(organizationSlug)
    }

    setLoading(true)
    try {
      const schema = await fetchPublicSchema(nextOrigin)
      const nextOperations = listOperations(schema)
      if (!nextOperations.length) {
        throw new Error("The OpenAPI document contains no supported operations.")
      }
      setOrigin(nextOrigin)
      setDocument(schema)
      setSelectedOperationId(nextOperations[0].id)
    } catch (caught) {
      setDocument(undefined)
      setOrigin("")
      setConnectionError(
        caught instanceof Error ? caught.message : "Unable to load the public API schema.",
      )
    } finally {
      setLoading(false)
    }
  }

  const previewOrigin =
    useLocalApi && localAvailable
      ? LOCAL_API_ORIGIN
      : validateOrganizationSlug(organizationSlug)
        ? "https://api.{organization-slug}.backfield.news"
        : deriveApiOrigin(organizationSlug)

  return (
    <div className="app-shell">
      <header className="site-header">
        <div>
          <p className="eyebrow">Backfield developer tools</p>
          <h1>Public API Playground</h1>
          <p className="site-subtitle">Schema-driven requests for the Backfield public API.</p>
        </div>
        <code>playground.backfield.news</code>
      </header>

      <section className="security-notice" aria-labelledby="security-title">
        <h2 id="security-title">Developer-only tool</h2>
        <p>
          Your project API key remains only in this tab’s React memory. It is never stored, added to
          the URL, logged, sent to analytics, or included verbatim in generated curl. Closing or
          refreshing this tab clears it.
        </p>
      </section>

      <section className="connection-card" aria-labelledby="connection-title">
        <h2 id="connection-title">Connect to an organization</h2>
        <div className="connection-grid">
          <div className="field">
            <label htmlFor="organization-slug">
              <span className="field-name">Organization slug</span>
              <span className="field-meta">Used only to derive the API hostname</span>
            </label>
            <input
              id="organization-slug"
              type="text"
              autoComplete="off"
              spellCheck={false}
              value={organizationSlug}
              disabled={useLocalApi}
              onChange={(event) => setOrganizationSlug(normalizeOrganizationSlug(event.target.value))}
              placeholder="example-newsroom"
            />
          </div>
          <div className="field">
            <label htmlFor="project-api-key">
              <span className="field-name">Project API key</span>
              <span className="field-meta">Held in memory only</span>
            </label>
            <div className="secret-row">
              <input
                id="project-api-key"
                type="password"
                autoComplete="off"
                value={apiKey}
                onChange={(event) => setApiKey(event.target.value)}
                placeholder="Paste a project API key"
              />
              <button type="button" className="secondary-button" onClick={() => setApiKey("")}>
                Clear key
              </button>
            </div>
          </div>
        </div>
        {localAvailable && (
          <label className="local-option">
            <input
              type="checkbox"
              checked={useLocalApi}
              onChange={(event) => setUseLocalApi(event.target.checked)}
            />
            Explicitly use the local Core API at {LOCAL_API_ORIGIN}
          </label>
        )}
        <div className="origin-preview">
          API origin: <code>{previewOrigin}</code>
        </div>
        <button className="connect-button" type="button" disabled={loading} onClick={connect}>
          {loading ? "Loading schema…" : "Load API schema"}
        </button>
        {connectionError && (
          <p className="error-message" role="alert">
            {connectionError}
          </p>
        )}
      </section>

      {document && selectedOperation && (
        <main className="explorer-layout">
          <nav className="endpoint-navigation" aria-label="Public API endpoints">
            <div className="schema-summary">
              <strong>{document.info.title}</strong>
              <span>Version {document.info.version}</span>
              <span>{operations.length} operations</span>
            </div>
            <label className="filter-label" htmlFor="endpoint-filter">
              Filter endpoints
            </label>
            <input
              id="endpoint-filter"
              type="search"
              value={filter}
              onChange={(event) => setFilter(event.target.value)}
              placeholder="Method, path, or summary"
            />
            <div className="endpoint-groups">
              {visibleGroups.map((group) => (
                <section key={group.name} className="endpoint-group">
                  <h2>{group.name}</h2>
                  {group.operations.map((operation) => (
                    <button
                      key={operation.id}
                      type="button"
                      className={`endpoint-link ${
                        operation.id === selectedOperation.id ? "endpoint-link-active" : ""
                      }`}
                      aria-current={operation.id === selectedOperation.id ? "page" : undefined}
                      onClick={() => setSelectedOperationId(operation.id)}
                    >
                      <span className={`method method-${operation.method}`}>
                        {operation.method.toUpperCase()}
                      </span>
                      <span>
                        <code>{operation.path}</code>
                        <small>{operation.summary}</small>
                      </span>
                    </button>
                  ))}
                </section>
              ))}
              {!visibleGroups.length && <p className="empty-message">No matching endpoints.</p>}
            </div>
          </nav>
          <EndpointExplorer
            key={`${origin}:${selectedOperation.id}`}
            document={document}
            operation={selectedOperation}
            origin={origin}
            apiKey={apiKey}
          />
        </main>
      )}
    </div>
  )
}
