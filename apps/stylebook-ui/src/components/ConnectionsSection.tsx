import { useState, useEffect, useCallback } from "react"
import { useAppMessage } from "@/components/AppMessageProvider"
import type { Connection } from "@/lib/stylebook-api/connections"
import {
  CONNECTIONS_PER_PAGE,
  listStylebookConnectionsForLocation,
  listStylebookConnectionsForOrganization,
  listStylebookConnectionsForPerson,
  listStylebookConnectionNatures,
  createStylebookConnectionForLocation,
  createStylebookConnectionForOrganization,
  createStylebookConnectionForPerson,
  updateStylebookConnectionForLocation,
  updateStylebookConnectionForOrganization,
  updateStylebookConnectionForPerson,
  closeStylebookConnectionForLocation,
  closeStylebookConnectionForOrganization,
  closeStylebookConnectionForPerson,
  reopenStylebookConnectionForLocation,
  reopenStylebookConnectionForOrganization,
  reopenStylebookConnectionForPerson,
} from "@/lib/stylebook-api/connections"
import {
  fetchConnectionNeighborhood,
  type ConnectionNeighborhood,
} from "@/lib/connectionGraph"
import type { GraphEntityProfileLines } from "@/lib/connectionGraphEntityProfile"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Plus, Pencil, Ban, RotateCcw, ExternalLink, List, Network } from "lucide-react"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import LocationSelector from "@/components/LocationSelector"
import PersonSelector from "@/components/PersonSelector"
import OrganizationSelector from "@/components/OrganizationSelector"
import ConnectionEvidenceBlock from "@/components/ConnectionEvidenceBlock"
import ConnectionsGraph from "@/components/ConnectionsGraph"
import NatureAutocomplete from "@/components/NatureAutocomplete"
import Pagination from "@/components/Pagination"
import { bestEvidenceRecord, formatConnectionSummaryLabel } from "@/lib/connectionEvidence"
import type { EntityType as ConnectionsEntityType } from "@/lib/entityTypes"
import { useProjectCatalogScope } from "@/lib/catalogNavigation"
import { fetchProjects, type Project } from "@/lib/stylebook-api/projects"

export type EntityType = ConnectionsEntityType

interface ConnectionsSectionProps {
  entityType: EntityType
  entityId: string | number
  stylebookSlug: string
  entityDisplayName: string
  entityProfileLines?: GraphEntityProfileLines
}

function getDetailUrl(
  entityType: EntityType,
  entityId: string | number,
  catalogBasePath: string,
  scopeSuffix: string,
): string {
  const base = window.location.origin
  const prefix = `${base}${catalogBasePath}`
  if (entityType === "person") {
    return `${prefix}/people/canonical/${entityId}${scopeSuffix}`
  }
  if (entityType === "organization") {
    return `${prefix}/organizations/canonical/${entityId}${scopeSuffix}`
  }
  if (entityType === "work") {
    return `${prefix}/works/canonical/${entityId}${scopeSuffix}`
  }
  return `${prefix}/locations/canonical/${entityId}${scopeSuffix}`
}

function connectionSummaryLabel(conn: Connection): string {
  return formatConnectionSummaryLabel(conn)
}

export default function ConnectionsSection({
  entityType,
  entityId,
  stylebookSlug,
  entityDisplayName,
  entityProfileLines,
}: ConnectionsSectionProps) {
  const { catalogScopeSuffix, catalogBasePath, projectScopeSlug } = useProjectCatalogScope()
  const { showError } = useAppMessage()
  const [connections, setConnections] = useState<Connection[]>([])
  const [connectionsTotal, setConnectionsTotal] = useState(0)
  const [connectionsPage, setConnectionsPage] = useState(1)
  const [graphNeighborhood, setGraphNeighborhood] = useState<ConnectionNeighborhood | null>(null)
  const [graphLoading, setGraphLoading] = useState(false)
  const [activeTab, setActiveTab] = useState<"list" | "graph">("list")
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [projects, setProjects] = useState<Project[]>([])

  const [addOpen, setAddOpen] = useState(false)
  const [selectorOpen, setSelectorOpen] = useState(false)
  const [selectedTargetId, setSelectedTargetId] = useState<string | number | null>(null)
  const [selectedTargetName, setSelectedTargetName] = useState<string | null>(null)
  const [addTargetType, setAddTargetType] = useState<
    'person' | 'location' | 'organization'
  >('person')
  const [nature, setNature] = useState('')
  const [description, setDescription] = useState('')
  const [natureSuggestions, setNatureSuggestions] = useState<string[]>([])
  const [natureSearch, setNatureSearch] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const [editConnection, setEditConnection] = useState<Connection | null>(null)
  const [editNature, setEditNature] = useState('')
  const [editDescription, setEditDescription] = useState('')
  const [editNatureSuggestions, setEditNatureSuggestions] = useState<string[]>([])
  const [editSubmitting, setEditSubmitting] = useState(false)

  const [deleteConnection, setDeleteConnection] = useState<Connection | null>(null)
  const [deleting, setDeleting] = useState(false)
  const selectorProjectSlug = projectScopeSlug || projects[0]?.slug || ""

  useEffect(() => {
    let active = true
    void fetchProjects()
      .then((rows) => {
        if (active) setProjects(rows)
      })
      .catch(() => {
        if (active) setProjects([])
      })
    return () => {
      active = false
    }
  }, [])

  const fetchConnectionsPage = useCallback(
    async (pageNum: number) => {
      setLoading(true)
      setError(null)
      try {
        const canonicalId = String(entityId)
        const offset = (pageNum - 1) * CONNECTIONS_PER_PAGE
        const options = {
          limit: CONNECTIONS_PER_PAGE,
          offset,
          includeClosed: false,
        }
        let res: Awaited<ReturnType<typeof listStylebookConnectionsForLocation>>
        if (entityType === "location") {
          res = await listStylebookConnectionsForLocation(stylebookSlug, canonicalId, options)
        } else if (entityType === "person") {
          res = await listStylebookConnectionsForPerson(stylebookSlug, canonicalId, options)
        } else if (entityType === "organization") {
          res = await listStylebookConnectionsForOrganization(
            stylebookSlug,
            canonicalId,
            options,
          )
        } else {
          setConnections([])
          setConnectionsTotal(0)
          return
        }
        setConnections(res.connections)
        setConnectionsTotal(res.total)
        const totalPages = Math.max(1, Math.ceil(res.total / CONNECTIONS_PER_PAGE))
        if (pageNum > totalPages && res.total > 0) {
          setConnectionsPage(totalPages)
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to load connections')
      } finally {
        setLoading(false)
      }
    },
    [entityType, entityId, stylebookSlug],
  )

  const fetchGraphConnections = useCallback(async () => {
    setGraphLoading(true)
    try {
      const neighborhood = await fetchConnectionNeighborhood(
        stylebookSlug,
        {
          entityType,
          entityId: String(entityId),
          displayName: entityDisplayName,
        },
        {
          includeClosed: false,
          expandHops: entityType === "person" ? 2 : 1,
        },
      )
      setGraphNeighborhood(neighborhood)
    } catch (e) {
      showError(e instanceof Error ? e.message : "Failed to load connection graph")
      setGraphNeighborhood({
        connections: [],
        hop1ConnectionCount: 0,
        hop2ConnectionCount: 0,
        neighborsExpanded: 0,
        neighborsSkipped: 0,
      })
    } finally {
      setGraphLoading(false)
    }
  }, [entityType, entityId, entityDisplayName, stylebookSlug, showError])

  useEffect(() => {
    setConnectionsPage(1)
    setGraphNeighborhood(null)
  }, [entityType, entityId, stylebookSlug])

  useEffect(() => {
    void fetchConnectionsPage(connectionsPage)
  }, [connectionsPage, fetchConnectionsPage])

  useEffect(() => {
    if (activeTab !== "graph" || graphNeighborhood !== null) return
    void fetchGraphConnections()
  }, [activeTab, graphNeighborhood, fetchGraphConnections])

  const refreshConnections = useCallback(() => {
    setGraphNeighborhood(null)
    void fetchConnectionsPage(connectionsPage)
    if (activeTab === "graph") {
      void fetchGraphConnections()
    }
  }, [activeTab, connectionsPage, fetchConnectionsPage, fetchGraphConnections])

  // Nature typeahead for add form
  useEffect(() => {
    if (!addOpen) return
    const q = natureSearch.trim() || nature
    listStylebookConnectionNatures(stylebookSlug, q || undefined).then((r) =>
      setNatureSuggestions(r.natures)
    )
  }, [addOpen, stylebookSlug, natureSearch, nature])

  // Nature typeahead for edit form
  useEffect(() => {
    if (!editConnection) return
    listStylebookConnectionNatures(stylebookSlug, editNature.trim() || undefined).then((r) =>
      setEditNatureSuggestions(r.natures)
    )
  }, [editConnection, stylebookSlug, editNature])

  const handleAddOpen = () => {
    setAddOpen(true)
    setSelectedTargetId(null)
    setSelectedTargetName(null)
    setAddTargetType(
      entityType === 'location' ? 'person' : entityType === 'person' ? 'location' : 'person'
    )
    setNature('')
    setDescription('')
    setNatureSearch('')
  }

  const handleAddSubmit = async () => {
    if (selectedTargetId == null) return
    const trimmedNature = nature.trim()
    const trimmedDescription = description.trim()
    if (!trimmedNature && !trimmedDescription) return
    const toType = addTargetType
    const body = {
      to_entity_type: toType,
      to_entity_id: selectedTargetId,
      ...(trimmedNature ? { nature: trimmedNature } : {}),
      ...(trimmedDescription ? { description: trimmedDescription } : {}),
    }
    const canonicalId = String(entityId)
    setSubmitting(true)
    try {
      if (entityType === "location") {
        await createStylebookConnectionForLocation(stylebookSlug, canonicalId, body)
      } else if (entityType === "person") {
        await createStylebookConnectionForPerson(stylebookSlug, canonicalId, body)
      } else if (entityType === "organization") {
        await createStylebookConnectionForOrganization(stylebookSlug, canonicalId, body)
      } else {
        throw new Error("Connections cannot be added from this entity type yet.")
      }
      setAddOpen(false)
      refreshConnections()
    } catch (e) {
      showError(e instanceof Error ? e.message : "Failed to create connection")
    } finally {
      setSubmitting(false)
    }
  }

  const handleEditOpen = (conn: Connection) => {
    setEditConnection(conn)
    setEditNature(conn.nature ?? '')
    setEditDescription(conn.description ?? '')
  }

  const handleEditSubmit = async () => {
    if (!editConnection) return
    const trimmedNature = editNature.trim()
    const trimmedDescription = editDescription.trim()
    if (!trimmedNature && !trimmedDescription) return
    const canonicalId = String(entityId)
    const body = {
      nature: trimmedNature || null,
      description: trimmedDescription || null,
    }
    setEditSubmitting(true)
    try {
      if (entityType === "location") {
        await updateStylebookConnectionForLocation(
          stylebookSlug,
          canonicalId,
          editConnection.id,
          body,
        )
      } else if (entityType === "person") {
        await updateStylebookConnectionForPerson(
          stylebookSlug,
          canonicalId,
          editConnection.id,
          body,
        )
      } else if (entityType === "organization") {
        await updateStylebookConnectionForOrganization(
          stylebookSlug,
          canonicalId,
          editConnection.id,
          body,
        )
      } else {
        throw new Error("Connections cannot be edited from this entity type yet.")
      }
      setEditConnection(null)
      refreshConnections()
    } catch (e) {
      showError(e instanceof Error ? e.message : "Failed to update connection")
    } finally {
      setEditSubmitting(false)
    }
  }

  const handleDeleteConfirm = async () => {
    if (!deleteConnection) return
    const canonicalId = String(entityId)
    setDeleting(true)
    try {
      if (entityType === "location") {
        await closeStylebookConnectionForLocation(
          stylebookSlug,
          canonicalId,
          deleteConnection.id,
        )
      } else if (entityType === "person") {
        await closeStylebookConnectionForPerson(
          stylebookSlug,
          canonicalId,
          deleteConnection.id,
        )
      } else if (entityType === "organization") {
        await closeStylebookConnectionForOrganization(
          stylebookSlug,
          canonicalId,
          deleteConnection.id,
        )
      } else {
        throw new Error("Connections cannot be closed from this entity type yet.")
      }
      setDeleteConnection(null)
      refreshConnections()
    } catch (e) {
      showError(e instanceof Error ? e.message : "Failed to close connection")
    } finally {
      setDeleting(false)
    }
  }

  const handleReopen = async (conn: Connection) => {
    const canonicalId = String(entityId)
    try {
      if (entityType === "location") {
        await reopenStylebookConnectionForLocation(stylebookSlug, canonicalId, conn.id)
      } else if (entityType === "person") {
        await reopenStylebookConnectionForPerson(stylebookSlug, canonicalId, conn.id)
      } else if (entityType === "organization") {
        await reopenStylebookConnectionForOrganization(stylebookSlug, canonicalId, conn.id)
      } else {
        throw new Error("Connections cannot be reopened from this entity type yet.")
      }
      refreshConnections()
    } catch (e) {
      showError(e instanceof Error ? e.message : "Failed to reopen connection")
    }
  }

  const isFrom = (conn: Connection) =>
    conn.from_entity_type === entityType && String(conn.from_entity_id) === String(entityId)
  const otherDisplayName = (conn: Connection) =>
    isFrom(conn) ? conn.to_display_name : conn.from_display_name
  const otherType = (conn: Connection): EntityType =>
    (isFrom(conn) ? conn.to_entity_type : conn.from_entity_type) as EntityType
  const otherId = (conn: Connection) => (isFrom(conn) ? conn.to_entity_id : conn.from_entity_id)
  const connectionsTotalPages = Math.max(
    1,
    Math.ceil(connectionsTotal / CONNECTIONS_PER_PAGE),
  )

  return (
    <>
      <Card>
        <CardHeader>
          <div className="flex flex-row items-start justify-between gap-4">
            <div className="space-y-1.5 min-w-0">
              <CardTitle>Connections</CardTitle>
              <CardDescription>
                Links between this {entityType} and other catalog entries.
              </CardDescription>
            </div>
            <div className="flex shrink-0 items-center gap-3">
              <Button
                type="button"
                className="shrink-0"
                onClick={handleAddOpen}
                disabled={loading || entityType === "work"}
              >
                <Plus className="h-4 w-4 mr-2" />
                Add connection
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {loading && connectionsTotal === 0 && !error && (
            <div className="text-center py-4">Loading connections...</div>
          )}
          {error && (
            <div className="text-center py-4 text-destructive">{error}</div>
          )}
          {!error && (connectionsTotal > 0 || !loading) && (
            <Tabs
              value={activeTab}
              onValueChange={(value) => setActiveTab(value as "list" | "graph")}
              className="w-full"
            >
              <TabsList>
                <TabsTrigger value="list">
                  <List className="h-4 w-4 mr-2" />
                  List
                </TabsTrigger>
                <TabsTrigger value="graph">
                  <Network className="h-4 w-4 mr-2" />
                  Graph
                </TabsTrigger>
              </TabsList>
              <TabsContent value="list" className="mt-4">
                {connectionsTotal === 0 ? (
                  <div className="text-center py-4 text-muted-foreground">No connections yet.</div>
                ) : (
                  <>
                  <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Connection</TableHead>
                  <TableHead className="w-[120px]">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {connections.map((conn) => (
                  <TableRow key={conn.id}>
                    <TableCell className="align-top">
                      <div className="text-sm">
                        {isFrom(conn) ? (
                          <>
                            <span className="font-medium">{entityDisplayName}</span>
                            <span className="mx-1 text-muted-foreground">→</span>
                            <a
                              href={getDetailUrl(
                                otherType(conn),
                                otherId(conn),
                                catalogBasePath,
                                catalogScopeSuffix,
                              )}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-primary hover:underline inline-flex items-center gap-0.5"
                            >
                              {conn.to_display_name}
                              <ExternalLink className="h-3 w-3 shrink-0 opacity-60" />
                            </a>
                          </>
                        ) : (
                          <>
                            <a
                              href={getDetailUrl(
                                otherType(conn),
                                otherId(conn),
                                catalogBasePath,
                                catalogScopeSuffix,
                              )}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-primary hover:underline inline-flex items-center gap-0.5"
                            >
                              {conn.from_display_name}
                              <ExternalLink className="h-3 w-3 shrink-0 opacity-60" />
                            </a>
                            <span className="mx-1 text-muted-foreground">→</span>
                            <span className="font-medium">{entityDisplayName}</span>
                          </>
                        )}
                      </div>
                      <p className="mt-0.5 text-sm text-foreground">
                        {connectionSummaryLabel(conn)}
                        {conn.closed_at ? (
                          <span className="ml-2 text-xs text-muted-foreground">(closed)</span>
                        ) : null}
                      </p>
                      {conn.nature?.trim() ? (
                        <p className="mt-0.5 text-xs text-muted-foreground">{conn.nature.replace(/_/g, " ")}</p>
                      ) : null}
                      <ConnectionEvidenceBlock evidence={bestEvidenceRecord(conn)} />
                    </TableCell>
                    <TableCell className="align-top">
                      <div className="flex gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleEditOpen(conn)}
                          title="Edit connection"
                          disabled={Boolean(conn.closed_at)}
                        >
                          <Pencil className="h-4 w-4" />
                        </Button>
                        {conn.closed_at ? (
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => void handleReopen(conn)}
                            title="Reopen connection"
                          >
                            <RotateCcw className="h-4 w-4" />
                          </Button>
                        ) : (
                          <Button
                            variant="destructive"
                            size="sm"
                            onClick={() => setDeleteConnection(conn)}
                            title="Close connection"
                          >
                            <Ban className="h-4 w-4" />
                          </Button>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
                  <Pagination
                    className="mt-4"
                    page={connectionsPage}
                    perPage={CONNECTIONS_PER_PAGE}
                    total={connectionsTotal}
                    totalPages={connectionsTotalPages}
                    hasNext={connectionsPage < connectionsTotalPages}
                    hasPrev={connectionsPage > 1}
                    onPageChange={setConnectionsPage}
                    itemLabel="connections"
                  />
                  </>
                )}
              </TabsContent>
              <TabsContent value="graph" className="mt-4">
                {graphLoading ? (
                  <div className="text-center py-4 text-muted-foreground">
                    Loading graph...
                  </div>
                ) : (
                <ConnectionsGraph
                  entityType={entityType}
                  entityId={entityId}
                  entityDisplayName={entityDisplayName}
                  stylebookSlug={stylebookSlug}
                  projectSlug={projectScopeSlug || undefined}
                  centerProfileLines={entityProfileLines}
                  neighborhood={
                    graphNeighborhood ?? {
                      connections: [],
                      hop1ConnectionCount: 0,
                      hop2ConnectionCount: 0,
                      neighborsExpanded: 0,
                      neighborsSkipped: 0,
                    }
                  }
                />
                )}
              </TabsContent>
            </Tabs>
          )}
        </CardContent>
      </Card>

      {/* Add connection dialog */}
      <Dialog open={addOpen} onOpenChange={setAddOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add connection</DialogTitle>
            <DialogDescription>
              Connect this {entityType} to another canonical. Select the other entity and describe the
              relationship (e.g. mayor, born in).
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div>
              <div className="mb-3">
                <Label>Connect to</Label>
                <div className="flex gap-2 mt-1 flex-wrap">
                  <Button
                    type="button"
                    variant={addTargetType === 'person' ? 'default' : 'outline'}
                    size="sm"
                    onClick={() => {
                      setAddTargetType('person')
                      setSelectedTargetId(null)
                      setSelectedTargetName(null)
                    }}
                  >
                    Person
                  </Button>
                  <Button
                    type="button"
                    variant={addTargetType === 'location' ? 'default' : 'outline'}
                    size="sm"
                    onClick={() => {
                      setAddTargetType('location')
                      setSelectedTargetId(null)
                      setSelectedTargetName(null)
                    }}
                  >
                    Location
                  </Button>
                  <Button
                    type="button"
                    variant={addTargetType === 'organization' ? 'default' : 'outline'}
                    size="sm"
                    onClick={() => {
                      setAddTargetType('organization')
                      setSelectedTargetId(null)
                      setSelectedTargetName(null)
                    }}
                  >
                    Organization
                  </Button>
                </div>
              </div>
              <Label>
                {addTargetType === 'person'
                  ? 'Person'
                  : addTargetType === 'location'
                    ? 'Location'
                    : 'Organization'}
              </Label>
              <div className="flex items-center gap-2 mt-1">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setSelectorOpen(true)}
                >
                  {selectedTargetId != null
                    ? (selectedTargetName || `Selected #${selectedTargetId}`)
                    : `Select ${addTargetType}`}
                </Button>
                {selectedTargetId != null && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      setSelectedTargetId(null)
                      setSelectedTargetName(null)
                    }}
                  >
                    Clear
                  </Button>
                )}
              </div>
              {addTargetType === 'person' ? (
                <PersonSelector
                  open={selectorOpen}
                  onOpenChange={setSelectorOpen}
                  projectSlug={selectorProjectSlug}
                  stylebookSlug={stylebookSlug}
                  excludeIds={entityType === 'person' ? [entityId] : undefined}
                  onSelect={(id, displayName) => {
                    setSelectedTargetId(id)
                    setSelectorOpen(false)
                    setSelectedTargetName(displayName ?? `Person #${id}`)
                  }}
                />
              ) : addTargetType === 'organization' ? (
                <OrganizationSelector
                  open={selectorOpen}
                  onOpenChange={setSelectorOpen}
                  projectSlug={selectorProjectSlug}
                  stylebookSlug={stylebookSlug}
                  excludeIds={entityType === 'organization' ? [entityId] : undefined}
                  onSelect={(id, displayName) => {
                    setSelectedTargetId(id)
                    setSelectorOpen(false)
                    setSelectedTargetName(displayName ?? `Organization #${id}`)
                  }}
                />
              ) : (
                <LocationSelector
                  open={selectorOpen}
                  onOpenChange={setSelectorOpen}
                  projectSlug={selectorProjectSlug}
                  stylebookSlug={stylebookSlug}
                  excludeIds={entityType === 'location' ? [entityId] : undefined}
                  onSelect={(id, displayName) => {
                    setSelectedTargetId(id)
                    setSelectorOpen(false)
                    setSelectedTargetName(displayName ?? `Location #${id}`)
                  }}
                />
              )}
            </div>
            <div>
              <Label htmlFor="connection-description">Description</Label>
              <Textarea
                id="connection-description"
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                placeholder="Describe the relationship in a sentence or less."
                className="mt-1"
                rows={3}
              />
            </div>
            <NatureAutocomplete
              label="Nature (optional)"
              value={nature}
              onChange={setNature}
              onSearchChange={setNatureSearch}
              suggestions={natureSuggestions}
              placeholder="e.g. works for, located at"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAddOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleAddSubmit}
              disabled={
                selectedTargetId == null ||
                (!nature.trim() && !description.trim()) ||
                submitting
              }
            >
              {submitting ? 'Adding...' : 'Add connection'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit connection dialog */}
      <Dialog open={!!editConnection} onOpenChange={(open) => !open && setEditConnection(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit connection</DialogTitle>
            <DialogDescription>
              Update the description or nature of this connection.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div>
              <Label htmlFor="edit-connection-description">Description</Label>
              <Textarea
                id="edit-connection-description"
                value={editDescription}
                onChange={(event) => setEditDescription(event.target.value)}
                placeholder="Describe the relationship in a sentence or less."
                className="mt-1"
                rows={3}
              />
            </div>
            <NatureAutocomplete
              label="Nature (optional)"
              value={editNature}
              onChange={setEditNature}
              suggestions={editNatureSuggestions}
              placeholder="e.g. works for, located at"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditConnection(null)}>
              Cancel
            </Button>
            <Button
              onClick={handleEditSubmit}
              disabled={(!editNature.trim() && !editDescription.trim()) || editSubmitting}
            >
              {editSubmitting ? 'Saving...' : 'Save'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete confirmation */}
      <Dialog open={!!deleteConnection} onOpenChange={(open) => !open && setDeleteConnection(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Close connection</DialogTitle>
            <DialogDescription>
              Close the connection between &quot;{entityDisplayName}&quot; and &quot;
              {deleteConnection && otherDisplayName(deleteConnection)}&quot;
              {deleteConnection ? ` (${connectionSummaryLabel(deleteConnection)})` : ""}?
              You can show closed connections later and reopen them if needed.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteConnection(null)} disabled={deleting}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={handleDeleteConfirm} disabled={deleting}>
              {deleting ? 'Closing...' : 'Close connection'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
