import { useEffect, useMemo, useState } from "react"
import { TerminalSquare } from "lucide-react"
import { UserAccountMenu } from "@backfield/ui/UserAccountMenu"

import EndpointExplorer from "./components/EndpointExplorer"
import PlatformSidebar from "./components/PlatformSidebar"
import { fetchPublicSchema } from "./lib/api"
import { listOperations, type OpenApiDocument, type PlaygroundOperation } from "./lib/openapi"
import {
  deriveApiOrigin,
  deriveStylebookApiOrigin,
  deriveProductOrigin,
  isLocalPlaygroundHost,
  LOCAL_AGATE_ORIGIN,
  LOCAL_API_ORIGIN,
  LOCAL_STYLEBOOK_API_ORIGIN,
  organizationSlugFromPlaygroundHost,
} from "./lib/origin"
import {
  fetchPlatformContext,
  logoutSession,
  type PlatformContext,
} from "./lib/session"

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
  const organizationSlug = organizationSlugFromPlaygroundHost(window.location.hostname)
  const apiOrigin = localAvailable
    ? LOCAL_API_ORIGIN
    : organizationSlug
      ? deriveApiOrigin(organizationSlug)
      : ""
  const stylebookApiOrigin = localAvailable
    ? LOCAL_STYLEBOOK_API_ORIGIN
    : organizationSlug
      ? deriveStylebookApiOrigin(organizationSlug)
      : ""
  const agateOrigin = localAvailable
    ? LOCAL_AGATE_ORIGIN
    : organizationSlug
      ? deriveProductOrigin("agate", organizationSlug)
      : ""
  const [apiKey, setApiKey] = useState("")
  const [document, setDocument] = useState<OpenApiDocument>()
  const [platformContext, setPlatformContext] = useState<PlatformContext>()
  const [sessionError, setSessionError] = useState("")
  const [sessionLoading, setSessionLoading] = useState(false)
  const [origin, setOrigin] = useState("")
  const [selectedOperationId, setSelectedOperationId] = useState("")
  const [filter, setFilter] = useState("")
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set())
  const [loading, setLoading] = useState(false)
  const [connectionError, setConnectionError] = useState("")

  const operations = useMemo(() => (document ? listOperations(document) : []), [document])
  const visibleGroups = useMemo(() => {
    const query = filter.trim().toLowerCase()
    const visible = query
      ? operations.filter((operation) =>
          [
            operation.group,
            operation.method,
            operation.displayPath,
            operation.path,
            operation.summary,
          ]
            .join(" ")
            .toLowerCase()
            .includes(query),
        )
      : operations
    return groupOperations(visible)
  }, [filter, operations])
  const selectedOperation =
    operations.find((operation) => operation.id === selectedOperationId) ?? operations[0]

  function toggleGroup(groupName: string) {
    setCollapsedGroups((current) => {
      const next = new Set(current)
      if (next.has(groupName)) {
        next.delete(groupName)
      } else {
        next.add(groupName)
      }
      return next
    })
  }

  async function loadSessionContext(
    coreOrigin: string,
    stylebookApiOrigin: string,
  ): Promise<PlatformContext> {
    setSessionLoading(true)
    setSessionError("")
    try {
      const context = await fetchPlatformContext(coreOrigin, stylebookApiOrigin)
      setPlatformContext(context)
      return context
    } catch (caught) {
      setPlatformContext(undefined)
      const message =
        caught instanceof Error
          ? caught.message
          : "Sign in to Backfield before opening the API Playground."
      setSessionError(message)
      throw caught
    } finally {
      setSessionLoading(false)
    }
  }

  useEffect(() => {
    if (!apiOrigin || !stylebookApiOrigin) {
      setSessionError(
        "Open the API Playground from your organization’s tenant-specific Playground domain.",
      )
      return
    }
    void loadSessionContext(apiOrigin, stylebookApiOrigin).catch(() => undefined)
    // Tenant origins are intentionally inferred once from the current hostname.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function connect() {
    setConnectionError("")
    if (!apiOrigin || !stylebookApiOrigin) {
      setConnectionError(
        "The current hostname does not identify a Backfield organization.",
      )
      return
    }

    setLoading(true)
    try {
      await loadSessionContext(apiOrigin, stylebookApiOrigin)
      const schema = await fetchPublicSchema(apiOrigin)
      const nextOperations = listOperations(schema)
      if (!nextOperations.length) {
        throw new Error("The OpenAPI document contains no supported operations.")
      }
      setOrigin(apiOrigin)
      setDocument(schema)
      setSelectedOperationId(nextOperations[0].id)
      setCollapsedGroups(new Set())
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

  async function logout() {
    if (apiOrigin) {
      await logoutSession(apiOrigin)
    }
    window.location.assign(agateOrigin ? `${agateOrigin}/login` : "/")
  }

  return (
    <div className="app-frame">
      <header className="site-header">
        <div className="product-brand">
          <TerminalSquare className="product-mark" strokeWidth={1.75} aria-hidden />
          <div>
            <h1>API Playground</h1>
            <p className="site-subtitle">Explore and test the Backfield public API</p>
          </div>
        </div>
        {platformContext ? (
          <UserAccountMenu
            userLabel={platformContext.user.email}
            onChangePassword={() =>
              window.location.assign(`${agateOrigin}/account/password`)
            }
            onLogout={() => void logout()}
          />
        ) : (
          <span className="developer-label">Backfield developer tools</span>
        )}
      </header>

      <div className="platform-shell">
        {platformContext && (
          <PlatformSidebar
            context={platformContext}
            organizationSlug={organizationSlug}
            local={localAvailable}
          />
        )}
        <main className="app-content">
        {sessionLoading && !platformContext && (
          <p className="session-status" role="status">
            Loading your Backfield workspace…
          </p>
        )}
        {sessionError && (
          <p className="session-error" role="alert">
            {sessionError}
          </p>
        )}
        <section
          className="connection-card"
          aria-labelledby="connection-title"
          aria-busy={loading}
        >
          <div className="section-heading">
            <div>
              <h2 id="connection-title">Connect to the API</h2>
              <p>Enter a project API key, then load this organization’s API contract.</p>
            </div>
          </div>
          <div className="connection-grid connection-grid-key-only">
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
                  Clear
                </button>
              </div>
            </div>
          </div>
          <div className="connection-actions">
            <button
              className="connect-button"
              type="button"
              disabled={loading || !apiOrigin}
              onClick={connect}
            >
              {loading ? "Loading schema…" : "Load API schema"}
            </button>
            <div className="origin-preview">
              API origin <code>{apiOrigin || "Unavailable for this hostname"}</code>
            </div>
          </div>
          {connectionError && (
            <p id="connection-error" className="error-message" role="alert">
              {connectionError}
            </p>
          )}
        </section>

        {document && selectedOperation && (
          <div className="explorer-layout">
            <nav className="endpoint-navigation" aria-label="Public API endpoints">
              <div className="schema-summary">
                <strong>{document.info.title}</strong>
                <span>
                  Version {document.info.version} · {operations.length} operations
                </span>
              </div>
              <label className="filter-label" htmlFor="endpoint-filter">
                Filter endpoints
              </label>
              <input
                id="endpoint-filter"
                type="search"
                value={filter}
                onChange={(event) => setFilter(event.target.value)}
                placeholder="Action, resource, or path"
              />
              <div className="endpoint-groups">
                {visibleGroups.map((group) => {
                  const expanded = !collapsedGroups.has(group.name)
                  const endpointLabel =
                    group.operations.length === 1 ? "1 endpoint" : `${group.operations.length} endpoints`
                  return (
                    <section key={group.name} className="endpoint-group">
                      <h2>
                        <button
                          type="button"
                          className="endpoint-group-toggle"
                          aria-expanded={expanded}
                          aria-label={`${group.name}, ${endpointLabel}`}
                          onClick={() => toggleGroup(group.name)}
                        >
                          <span className="endpoint-group-name">
                            <span className="endpoint-group-chevron" aria-hidden>
                              {expanded ? "⌄" : "›"}
                            </span>
                            <span>{group.name}</span>
                          </span>
                          <span>{group.operations.length}</span>
                        </button>
                      </h2>
                      {expanded &&
                        group.operations.map((operation) => (
                          <button
                            key={operation.id}
                            type="button"
                            className={`endpoint-link ${
                              operation.id === selectedOperation.id ? "endpoint-link-active" : ""
                            }`}
                            aria-current={
                              operation.id === selectedOperation.id ? "page" : undefined
                            }
                            onClick={() => setSelectedOperationId(operation.id)}
                          >
                            <span className={`method method-${operation.method}`}>
                              {operation.method.toUpperCase()}
                            </span>
                            <span className="endpoint-details">
                              <span className="endpoint-summary">{operation.summary}</span>
                              <code title={operation.path}>{operation.displayPath}</code>
                            </span>
                          </button>
                        ))}
                    </section>
                  )
                })}
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
          </div>
        )}
        </main>
      </div>
    </div>
  )
}
