import { useEffect, useMemo, useState } from "react"
import { CircleUserRound, TerminalSquare } from "lucide-react"
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

const API_KEY_SESSION_STORAGE = "backfield-playground-project-api-key"
const SELECTED_OPERATION_SESSION_STORAGE = "backfield-playground-selected-operation"
const ENDPOINT_FILTER_SESSION_STORAGE = "backfield-playground-endpoint-filter"
const EXPANDED_GROUPS_SESSION_STORAGE = "backfield-playground-expanded-groups"

function readSessionValue(key: string): string {
  try {
    return sessionStorage.getItem(key) ?? ""
  } catch {
    return ""
  }
}

function readExpandedGroups(): Set<string> {
  try {
    const parsed = JSON.parse(
      sessionStorage.getItem(EXPANDED_GROUPS_SESSION_STORAGE) ?? "[]",
    ) as unknown
    return new Set(
      Array.isArray(parsed)
        ? parsed.filter((group): group is string => typeof group === "string")
        : [],
    )
  } catch {
    return new Set()
  }
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
  const [apiKey, setApiKey] = useState(() => readSessionValue(API_KEY_SESSION_STORAGE))
  const [apiKeyDraft, setApiKeyDraft] = useState(apiKey)
  const [document, setDocument] = useState<OpenApiDocument>()
  const [platformContext, setPlatformContext] = useState<PlatformContext>()
  const [sessionError, setSessionError] = useState("")
  // Start loading when this hostname can resolve an API origin so the header
  // and sidebar reserve space instead of flashing empty chrome.
  const [sessionLoading, setSessionLoading] = useState(
    () => Boolean(apiOrigin && stylebookApiOrigin),
  )
  const [origin, setOrigin] = useState("")
  const [selectedOperationId, setSelectedOperationId] = useState(() =>
    readSessionValue(SELECTED_OPERATION_SESSION_STORAGE),
  )
  const [filter, setFilter] = useState(() =>
    readSessionValue(ENDPOINT_FILTER_SESSION_STORAGE),
  )
  const [explorerProjectSlug, setExplorerProjectSlug] = useState("")
  // Endpoint groups start collapsed; users expand only what they need.
  const [expandedGroups, setExpandedGroups] =
    useState<Set<string>>(readExpandedGroups)
  const [loading, setLoading] = useState(false)
  const [connectionError, setConnectionError] = useState("")

  useEffect(() => {
    try {
      if (apiKey) {
        sessionStorage.setItem(API_KEY_SESSION_STORAGE, apiKey)
      } else {
        sessionStorage.removeItem(API_KEY_SESSION_STORAGE)
      }
    } catch {
      // Storage may be unavailable; the key remains usable in memory for this page.
    }
  }, [apiKey])

  useEffect(() => {
    try {
      if (selectedOperationId) {
        sessionStorage.setItem(
          SELECTED_OPERATION_SESSION_STORAGE,
          selectedOperationId,
        )
      }
      sessionStorage.setItem(ENDPOINT_FILTER_SESSION_STORAGE, filter)
      sessionStorage.setItem(
        EXPANDED_GROUPS_SESSION_STORAGE,
        JSON.stringify([...expandedGroups]),
      )
    } catch {
      // Navigation state persistence is an optional convenience.
    }
  }, [expandedGroups, filter, selectedOperationId])

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
  const projectOptions = useMemo(
    () =>
      (platformContext?.workspaces ?? [])
        .flatMap((workspace) =>
          workspace.projects.map((project) => ({
            value: project.slug,
            label: `${project.name} (${project.slug})`,
            group: workspace.name,
          })),
        )
        .sort(
          (left, right) =>
            left.group.localeCompare(right.group, undefined, { sensitivity: "base" }) ||
            left.label.localeCompare(right.label, undefined, { sensitivity: "base" }),
        ),
    [platformContext],
  )

  function toggleGroup(groupName: string) {
    setExpandedGroups((current) => {
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
    void loadSchema()
    // Tenant origins are intentionally inferred once from the current hostname.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function loadSchema() {
    setConnectionError("")
    if (!apiOrigin || !stylebookApiOrigin) {
      setConnectionError(
        "The current hostname does not identify a Backfield organization.",
      )
      return
    }

    setLoading(true)
    try {
      const schema = await fetchPublicSchema(apiOrigin)
      const nextOperations = listOperations(schema)
      if (!nextOperations.length) {
        throw new Error("The OpenAPI document contains no supported operations.")
      }
      setOrigin(apiOrigin)
      setDocument(schema)
      setSelectedOperationId((current) =>
        nextOperations.some((operation) => operation.id === current)
          ? current
          : nextOperations[0].id,
      )
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

  function clearApiKey() {
    setApiKey("")
    setApiKeyDraft("")
  }

  return (
    <div className="app-frame">
      <header className="site-header">
        <div className="product-brand">
          <h1>
            <TerminalSquare className="product-mark" strokeWidth={1.75} aria-hidden />
            API Playground
          </h1>
          <p className="site-subtitle">Explore and test the Backfield public API</p>
        </div>
        {platformContext ? (
          <UserAccountMenu
            userLabel={platformContext.user.email}
            onChangePassword={() =>
              window.location.assign(`${agateOrigin}/account/password`)
            }
            onLogout={() => void logout()}
          />
        ) : sessionLoading ? (
          <span
            className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-input bg-background text-muted-foreground shadow-sm"
            aria-hidden
          >
            <CircleUserRound className="h-5 w-5" />
          </span>
        ) : null}
      </header>

      <div className="platform-shell">
        {platformContext ? (
          <PlatformSidebar
            context={platformContext}
            organizationSlug={organizationSlug}
            local={localAvailable}
          />
        ) : sessionLoading ? (
          <aside
            className="flex flex-col border-r bg-muted/30 shrink-0 min-h-0 self-stretch w-56"
            aria-hidden
          />
        ) : null}
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
          className={`connection-card ${
            document && apiKey ? "connection-card-compact" : ""
          }`}
          aria-labelledby="connection-title"
          aria-busy={loading}
        >
          {document && apiKey ? (
            <div className="connection-compact-row">
              <div className="connection-compact-status">
                <span className="connection-status-dot" aria-hidden />
                <div>
                  <h2 id="connection-title">API schema loaded</h2>
                  <p>{document.info.title}</p>
                </div>
              </div>
              <div className="connection-compact-actions">
                <button
                  className="secondary-button"
                  type="button"
                  disabled={loading}
                  onClick={loadSchema}
                >
                  {loading ? "Reloading…" : "Reload schema"}
                </button>
                <button
                  className="secondary-button"
                  type="button"
                  onClick={clearApiKey}
                >
                  Clear key
                </button>
              </div>
            </div>
          ) : (
            <>
              <div className="section-heading">
                <div>
                  <h2 id="connection-title">
                    {document ? "Browse the API schema" : "API schema"}
                  </h2>
                  <p>
                    {document
                      ? "Browse every endpoint without authentication. Add a project API key to execute requests."
                      : loading
                        ? "Loading this organization’s public API schema…"
                        : "The public API schema is available without authentication. Add a project API key to execute requests."}
                  </p>
                </div>
              </div>
              <div className="connection-grid connection-grid-key-only">
                <div className="field">
                  <label htmlFor="project-api-key">
                    <span className="field-name">Project API key</span>
                  </label>
                  <div className="secret-row">
                    <input
                      id="project-api-key"
                      type="password"
                      autoComplete="off"
                      value={apiKeyDraft}
                      onChange={(event) => setApiKeyDraft(event.target.value)}
                      placeholder="Paste a project API key"
                    />
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={() => setApiKeyDraft("")}
                    >
                      Clear
                    </button>
                  </div>
                </div>
              </div>
              <div className="connection-actions">
                <button
                  className="connect-button"
                  type="button"
                  disabled={!apiKeyDraft.trim()}
                  onClick={() => setApiKey(apiKeyDraft.trim())}
                >
                  Use API key
                </button>
                <button
                  className="secondary-button"
                  type="button"
                  disabled={loading || !apiOrigin}
                  onClick={loadSchema}
                >
                  {loading
                    ? "Loading schema…"
                    : document
                      ? "Reload schema"
                      : "Retry schema"}
                </button>
                <div className="origin-preview">
                  API origin <code>{apiOrigin || "Unavailable for this hostname"}</code>
                </div>
              </div>
            </>
          )}
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
                placeholder="Action, resource, or path"
              />
              <div className="endpoint-groups">
                {visibleGroups.map((group) => {
                  // Filtering reveals matches even in groups the user has not expanded.
                  const expanded = filter.trim() !== "" || expandedGroups.has(group.name)
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
              projectOptions={projectOptions}
              projectSlug={explorerProjectSlug}
              onProjectSlugChange={setExplorerProjectSlug}
            />
          </div>
        )}
        </main>
      </div>
    </div>
  )
}
