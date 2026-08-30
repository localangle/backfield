import { Ban, Building2, ExternalLink, MapPin, RotateCcw, User, X } from "lucide-react"
import { useState } from "react"

import { useAppMessage } from "@/components/AppMessageProvider"
import ConnectionEvidenceBlock from "@/components/ConnectionEvidenceBlock"
import ConnectionStatusMeta from "@/components/ConnectionStatusMeta"
import { Button } from "@/components/ui/button"
import {
  bestEvidenceRecord,
  formatConnectionSummaryLabel,
} from "@/lib/connectionEvidence"
import {
  classifyConnectionHop,
  connectionsTouchingEntity,
  entityRefKey,
  formatNatureLabel,
  otherEndFromConnection,
  type GraphEntityRef,
  type GraphHop,
} from "@/lib/connectionGraph"
import { entityDetailUrl } from "@/lib/stylebookPaths"
import {
  useGraphEntityProfile,
  type GraphEntityProfileLines,
} from "@/lib/connectionGraphEntityProfile"
import {
  closeStylebookConnection,
  reopenStylebookConnection,
  type Connection,
} from "@/lib/stylebook-api/connections"
import type { EntityType as ConnectionsEntityType } from "@/lib/entityTypes"
import { entityDisplayName as catalogEntityLabel } from "@/lib/entityRegistry"
import { cn } from "@/lib/utils"

const ENTITY_ICON: Record<ConnectionsEntityType, typeof User> = {
  person: User,
  organization: Building2,
  location: MapPin,
  work: Building2,
}

export type GraphSelection =
  | { kind: "node"; entityType: ConnectionsEntityType; entityId: string }
  | { kind: "edge"; connectionIds: number[] }

interface ConnectionGraphDetailPanelProps {
  selection: GraphSelection
  center: GraphEntityRef
  connections: Connection[]
  connectionsById: Map<number, Connection>
  stylebookSlug: string
  projectSlug?: string
  centerProfileLines?: GraphEntityProfileLines
  catalogBasePath: string
  catalogScopeSuffix: string
  onClear: () => void
  onSelectConnection: (connectionIds: number[]) => void
  onSelectNode: (entityType: ConnectionsEntityType, entityId: string) => void
  onConnectionsChanged?: () => void
}

function useConnectionLifecycle(
  stylebookSlug: string,
  onConnectionsChanged?: () => void,
) {
  const { showConfirm, showError } = useAppMessage()
  const [busyId, setBusyId] = useState<number | null>(null)

  const closeConnection = async (conn: Connection) => {
    const summary = formatConnectionSummaryLabel(conn)
    const ok = await showConfirm(
      `Close the connection between "${conn.from_display_name}" and "${conn.to_display_name}"${
        summary ? ` (${summary})` : ""
      }? You can show closed connections later and reopen them if needed.`,
      {
        title: "Close connection",
        confirmLabel: "Close connection",
        cancelLabel: "Cancel",
        destructive: true,
      },
    )
    if (!ok) return
    setBusyId(conn.id)
    try {
      await closeStylebookConnection(stylebookSlug, conn)
      onConnectionsChanged?.()
    } catch (error) {
      showError(error instanceof Error ? error.message : "Failed to close connection")
    } finally {
      setBusyId(null)
    }
  }

  const reopenConnection = async (conn: Connection) => {
    setBusyId(conn.id)
    try {
      await reopenStylebookConnection(stylebookSlug, conn)
      onConnectionsChanged?.()
    } catch (error) {
      showError(error instanceof Error ? error.message : "Failed to reopen connection")
    } finally {
      setBusyId(null)
    }
  }

  return { busyId, closeConnection, reopenConnection }
}

function ConnectionLifecycleButtons({
  conn,
  busyId,
  onClose,
  onReopen,
  className,
}: {
  conn: Connection
  busyId: number | null
  onClose: (conn: Connection) => void
  onReopen: (conn: Connection) => void
  className?: string
}) {
  const busy = busyId === conn.id
  if (conn.closed_at) {
    return (
      <Button
        type="button"
        variant="outline"
        size="sm"
        className={cn("h-7 px-2", className)}
        disabled={busy}
        onClick={(event) => {
          event.stopPropagation()
          void onReopen(conn)
        }}
        title="Reopen connection"
      >
        <RotateCcw className="h-3.5 w-3.5" />
        <span className="ml-1.5 text-xs">Reopen</span>
      </Button>
    )
  }
  return (
    <Button
      type="button"
      variant="outline"
      size="sm"
      className={cn(
        "h-7 px-2 text-destructive hover:bg-destructive/10 hover:text-destructive",
        className,
      )}
      disabled={busy}
      onClick={(event) => {
        event.stopPropagation()
        void onClose(conn)
      }}
      title="Close connection"
    >
      <Ban className="h-3.5 w-3.5" />
      <span className="ml-1.5 text-xs">{busy ? "Closing…" : "Close"}</span>
    </Button>
  )
}

function ConnectionRow({
  conn,
  focusRef,
  catalogBasePath,
  catalogScopeSuffix,
  busyId,
  onSelect,
  onSelectConnection,
  onClose,
  onReopen,
}: {
  conn: Connection
  focusRef: GraphEntityRef
  catalogBasePath: string
  catalogScopeSuffix: string
  busyId: number | null
  onSelect: (entityType: ConnectionsEntityType, entityId: string) => void
  onSelectConnection: (connectionIds: number[]) => void
  onClose: (conn: Connection) => void
  onReopen: (conn: Connection) => void
}) {
  const other = otherEndFromConnection(conn, focusRef)
  if (!other) return null

  const nature = formatNatureLabel(conn.nature)
  const summary = formatConnectionSummaryLabel(conn)

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => onSelectConnection([conn.id])}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault()
          onSelectConnection([conn.id])
        }
      }}
      className="w-full cursor-pointer rounded-lg border border-transparent px-2.5 py-2 text-left transition-colors hover:border-border hover:bg-muted/40"
    >
      <div>
        <div className="min-w-0">
          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation()
              onSelect(other.entityType, other.entityId)
            }}
            className="w-full text-left text-sm font-medium text-foreground hover:text-primary hover:underline"
          >
            {other.displayName}
          </button>
          {nature ? (
            <p className="mt-0.5 text-xs font-medium text-primary">{nature}</p>
          ) : null}
          {summary && summary !== nature ? (
            <p className="mt-0.5 text-xs leading-snug text-muted-foreground line-clamp-2">
              {summary}
            </p>
          ) : null}
        </div>
      </div>
      <ConnectionStatusMeta conn={conn} compact />
      <div className="mt-1.5 flex flex-wrap items-center gap-2">
        <a
          href={entityDetailUrl(other.entityType, other.entityId, catalogBasePath, catalogScopeSuffix)}
          target="_blank"
          rel="noopener noreferrer"
          onClick={(event) => event.stopPropagation()}
          className="inline-flex items-center gap-1 text-[11px] text-muted-foreground hover:text-primary"
        >
          Open in Stylebook
          <ExternalLink className="h-3 w-3" />
        </a>
        <ConnectionLifecycleButtons
          conn={conn}
          busyId={busyId}
          onClose={onClose}
          onReopen={onReopen}
        />
      </div>
    </div>
  )
}

function ConnectionDetailCard({
  conn,
  busyId,
  onClose,
  onReopen,
}: {
  conn: Connection
  busyId: number | null
  onClose: (conn: Connection) => void
  onReopen: (conn: Connection) => void
}) {
  const nature = formatNatureLabel(conn.nature)
  const summary = formatConnectionSummaryLabel(conn)

  return (
    <div className="rounded-lg border bg-muted/10 px-3 py-2.5">
      <div className="mb-2 flex items-start justify-between gap-2">
        <div className="min-w-0">
          {nature ? (
            <p className="text-sm font-medium text-foreground">{nature}</p>
          ) : (
            <p className="text-sm font-medium text-foreground">Connection</p>
          )}
        </div>
        <ConnectionLifecycleButtons
          conn={conn}
          busyId={busyId}
          onClose={onClose}
          onReopen={onReopen}
        />
      </div>
      {summary && summary !== nature ? (
        <p className="text-sm leading-relaxed text-muted-foreground">{summary}</p>
      ) : null}
      <ConnectionStatusMeta conn={conn} />
      <ConnectionEvidenceBlock evidence={bestEvidenceRecord(conn)} />
    </div>
  )
}

function EntityProfileLines({
  lines,
  loading,
}: {
  lines: GraphEntityProfileLines
  loading: boolean
}) {
  if (loading && lines.length === 0) {
    return <p className="text-xs text-muted-foreground">Loading details…</p>
  }
  if (lines.length === 0) return null
  return (
    <div className="space-y-0.5">
      {lines.map((line) => (
        <p key={line} className="text-sm leading-snug text-muted-foreground">
          {line}
        </p>
      ))}
    </div>
  )
}

function EntityHeader({
  entityRef,
  hop,
  stylebookSlug,
  projectSlug,
  profileSeedLines,
  catalogBasePath,
  catalogScopeSuffix,
}: {
  entityRef: GraphEntityRef
  hop: GraphHop
  stylebookSlug: string
  projectSlug?: string
  profileSeedLines?: GraphEntityProfileLines
  catalogBasePath: string
  catalogScopeSuffix: string
}) {
  const seedLines =
    hop === 0 && profileSeedLines?.length ? profileSeedLines : undefined
  const { lines, loading } = useGraphEntityProfile(
    stylebookSlug,
    entityRef.entityType,
    entityRef.entityId,
    projectSlug,
    seedLines,
  )
  const Icon = ENTITY_ICON[entityRef.entityType]
  return (
    <div className="space-y-2">
      <div className="flex items-start gap-2.5">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-muted">
          <Icon className="h-4 w-4 text-muted-foreground" aria-hidden />
        </div>
        <div className="min-w-0">
          <p className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
            {catalogEntityLabel(entityRef.entityType)}
          </p>
          <h3 className="text-base font-semibold leading-snug">{entityRef.displayName}</h3>
          <div className="mt-1">
            <EntityProfileLines lines={lines} loading={loading} />
          </div>
        </div>
      </div>
      {hop !== 0 ? (
        <Button variant="outline" size="sm" className="w-full" asChild>
          <a
            href={entityDetailUrl(
              entityRef.entityType,
              entityRef.entityId,
              catalogBasePath,
              catalogScopeSuffix,
            )}
            target="_blank"
            rel="noopener noreferrer"
          >
            Open in Stylebook
            <ExternalLink className="ml-2 h-3.5 w-3.5" />
          </a>
        </Button>
      ) : null}
    </div>
  )
}

function nodeHop(
  entityRef: GraphEntityRef,
  center: GraphEntityRef,
): GraphHop {
  return entityRefKey(entityRef) === entityRefKey(center) ? 0 : 1
}

export default function ConnectionGraphDetailPanel({
  selection,
  center,
  connections,
  connectionsById,
  stylebookSlug,
  projectSlug,
  centerProfileLines,
  catalogBasePath,
  catalogScopeSuffix,
  onClear,
  onSelectConnection,
  onSelectNode,
  onConnectionsChanged,
}: ConnectionGraphDetailPanelProps) {
  const { busyId, closeConnection, reopenConnection } = useConnectionLifecycle(
    stylebookSlug,
    onConnectionsChanged,
  )

  if (selection.kind === "edge") {
    const selectedConnections = selection.connectionIds
      .map((id) => connectionsById.get(id))
      .filter((conn): conn is Connection => conn !== undefined)

    if (selectedConnections.length === 0) {
      return (
        <aside className="flex h-full w-[min(100%,320px)] shrink-0 flex-col border-l bg-background">
          <PanelChrome title="Connection" onClear={onClear}>
            <p className="text-sm text-muted-foreground">This connection is no longer in view.</p>
          </PanelChrome>
        </aside>
      )
    }

    const conn = selectedConnections[0]!
    const from: GraphEntityRef = {
      entityType: conn.from_entity_type as ConnectionsEntityType,
      entityId: String(conn.from_entity_id),
      displayName: conn.from_display_name,
    }
    const to: GraphEntityRef = {
      entityType: conn.to_entity_type as ConnectionsEntityType,
      entityId: String(conn.to_entity_id),
      displayName: conn.to_display_name,
    }
    const panelTitle =
      selectedConnections.length === 1
        ? "Connection"
        : `${selectedConnections.length} connections`

    return (
      <aside className="flex h-full w-[min(100%,320px)] shrink-0 flex-col border-l bg-background">
        <PanelChrome title={panelTitle} onClear={onClear}>
          <div className="space-y-4">
            <div className="space-y-2">
              <button
                type="button"
                onClick={() => onSelectNode(from.entityType, from.entityId)}
                className="block w-full rounded-md px-1 py-0.5 text-left text-sm font-medium hover:bg-muted/50 hover:text-primary"
              >
                {from.displayName}
              </button>
              <div className="flex items-center gap-2 px-1 text-xs text-muted-foreground">
                <span className="h-px flex-1 bg-border" />
                <span>
                  {selectedConnections.length === 1
                    ? formatNatureLabel(conn.nature) ?? "linked to"
                    : `${selectedConnections.length} relationships`}
                </span>
                <span className="h-px flex-1 bg-border" />
              </div>
              <button
                type="button"
                onClick={() => onSelectNode(to.entityType, to.entityId)}
                className="block w-full rounded-md px-1 py-0.5 text-left text-sm font-medium hover:bg-muted/50 hover:text-primary"
              >
                {to.displayName}
              </button>
            </div>

            <div className="space-y-2">
              {selectedConnections.map((row) => (
                <ConnectionDetailCard
                  key={row.id}
                  conn={row}
                  busyId={busyId}
                  onClose={closeConnection}
                  onReopen={reopenConnection}
                />
              ))}
            </div>
          </div>
        </PanelChrome>
      </aside>
    )
  }

  const entityRef: GraphEntityRef = {
    entityType: selection.entityType,
    entityId: selection.entityId,
    displayName:
      selection.entityType === center.entityType && selection.entityId === center.entityId
        ? center.displayName
        : connections
            .flatMap((conn) => [
              {
                entityType: conn.from_entity_type as ConnectionsEntityType,
                entityId: String(conn.from_entity_id),
                displayName: conn.from_display_name,
              },
              {
                entityType: conn.to_entity_type as ConnectionsEntityType,
                entityId: String(conn.to_entity_id),
                displayName: conn.to_display_name,
              },
            ])
            .find(
              (ref) =>
                ref.entityType === selection.entityType && ref.entityId === selection.entityId,
            )?.displayName ?? "Unknown",
  }

  const hop = nodeHop(entityRef, center)
  const profileSeedLines =
    entityRefKey(entityRef) === entityRefKey(center) ? centerProfileLines : undefined

  const entityConnections = connectionsTouchingEntity(connections, entityRef).sort((a, b) => {
    const hopA = classifyConnectionHop(a, center)
    const hopB = classifyConnectionHop(b, center)
    if (hopA !== hopB) return hopA - hopB
    const otherA = otherEndFromConnection(a, entityRef)?.displayName ?? ""
    const otherB = otherEndFromConnection(b, entityRef)?.displayName ?? ""
    return otherA.localeCompare(otherB, undefined, { sensitivity: "base" })
  })

  return (
    <aside className="flex h-full w-[min(100%,320px)] shrink-0 flex-col border-l bg-background">
      <PanelChrome
        title={hop === 0 ? "This entry" : "Connected entry"}
        onClear={onClear}
      >
        <div className="space-y-4">
          <EntityHeader
            entityRef={entityRef}
            hop={hop}
            stylebookSlug={stylebookSlug}
            projectSlug={projectSlug}
            profileSeedLines={profileSeedLines}
            catalogBasePath={catalogBasePath}
            catalogScopeSuffix={catalogScopeSuffix}
          />

          <div>
            <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
              {entityConnections.length === 1
                ? "1 connection in this view"
                : `${entityConnections.length} connections in this view`}
            </p>
            <div className="space-y-1">
              {entityConnections.map((conn) => (
                <ConnectionRow
                  key={conn.id}
                  conn={conn}
                  focusRef={entityRef}
                  catalogBasePath={catalogBasePath}
                  catalogScopeSuffix={catalogScopeSuffix}
                  busyId={busyId}
                  onSelect={onSelectNode}
                  onSelectConnection={onSelectConnection}
                  onClose={closeConnection}
                  onReopen={reopenConnection}
                />
              ))}
            </div>
          </div>
        </div>
      </PanelChrome>
    </aside>
  )
}

function PanelChrome({
  title,
  onClear,
  children,
}: {
  title: string
  onClear: () => void
  children: React.ReactNode
}) {
  return (
    <>
      <div className="flex items-center justify-between border-b px-3 py-2.5">
        <h2 className="text-sm font-semibold">{title}</h2>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-7 w-7"
          onClick={onClear}
          aria-label="Close details"
        >
          <X className="h-4 w-4" />
        </Button>
      </div>
      <div className={cn("flex-1 overflow-y-auto px-3 py-3")}>{children}</div>
    </>
  )
}
