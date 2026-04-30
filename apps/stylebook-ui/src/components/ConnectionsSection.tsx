import { useState, useEffect, useCallback } from "react"
import { useAppMessage } from "@/components/AppMessageProvider"
import type { Connection } from "@/lib/stylebook-api/connections"
import {
  listConnectionsForLocation,
  listConnectionNatures,
  createConnectionForLocation,
  updateConnectionForLocation,
  deleteConnectionForLocation,
} from "@/lib/stylebook-api/connections"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Plus, Pencil, Trash2, ExternalLink, List, Network } from "lucide-react"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import LocationSelector from "@/components/LocationSelector"
import PersonSelector from "@/components/PersonSelector"
import OrganizationSelector from "@/components/OrganizationSelector"
import WorkSelector from "@/components/WorkSelector"
import ConnectionsGraph from "@/components/ConnectionsGraph"
import NatureAutocomplete from "@/components/NatureAutocomplete"
import type { ConnectionsEntityType } from "@/lib/connectionsEntityTypes"

export type EntityType = ConnectionsEntityType

interface ConnectionsSectionProps {
  entityType: EntityType
  entityId: string | number
  projectSlug: string
  entityDisplayName: string
}

function getDetailUrl(entityType: EntityType, entityId: string | number, projectSlug: string): string {
  const base = window.location.origin
  if (entityType === 'person') {
    return `${base}/people/canonical/${entityId}?project=${projectSlug}`
  }
  if (entityType === 'organization') {
    return `${base}/organizations/canonical/${entityId}?project=${projectSlug}`
  }
  if (entityType === 'work') {
    return `${base}/works/canonical/${entityId}?project=${projectSlug}`
  }
  return `${base}/locations/canonical/${entityId}?project=${projectSlug}`
}

export default function ConnectionsSection({
  entityType,
  entityId,
  projectSlug,
  entityDisplayName,
}: ConnectionsSectionProps) {
  const { showError } = useAppMessage()
  const [connections, setConnections] = useState<Connection[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [addOpen, setAddOpen] = useState(false)
  const [selectorOpen, setSelectorOpen] = useState(false)
  const [selectedTargetId, setSelectedTargetId] = useState<string | number | null>(null)
  const [selectedTargetName, setSelectedTargetName] = useState<string | null>(null)
  const [addTargetType, setAddTargetType] = useState<'person' | 'location' | 'organization' | 'work'>('person')
  const [nature, setNature] = useState('')
  const [natureSuggestions, setNatureSuggestions] = useState<string[]>([])
  const [natureSearch, setNatureSearch] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const [editConnection, setEditConnection] = useState<Connection | null>(null)
  const [editNature, setEditNature] = useState('')
  const [editNatureSuggestions, setEditNatureSuggestions] = useState<string[]>([])
  const [editSubmitting, setEditSubmitting] = useState(false)

  const [deleteConnection, setDeleteConnection] = useState<Connection | null>(null)
  const [deleting, setDeleting] = useState(false)

  const fetchConnections = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      if (entityType === "location") {
        const res = await listConnectionsForLocation(String(entityId), projectSlug)
        setConnections(res.connections)
      } else {
        setConnections([])
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load connections')
    } finally {
      setLoading(false)
    }
  }, [entityType, entityId, projectSlug])

  useEffect(() => {
    fetchConnections()
  }, [fetchConnections])

  // Nature typeahead for add form
  useEffect(() => {
    if (!addOpen) return
    const q = natureSearch.trim() || nature
    listConnectionNatures(projectSlug, q || undefined).then((r) => setNatureSuggestions(r.natures))
  }, [addOpen, projectSlug, natureSearch, nature])

  // Nature typeahead for edit form
  useEffect(() => {
    if (!editConnection) return
    listConnectionNatures(projectSlug, editNature.trim() || undefined).then((r) =>
      setEditNatureSuggestions(r.natures)
    )
  }, [editConnection, projectSlug, editNature])

  const handleAddOpen = () => {
    setAddOpen(true)
    setSelectedTargetId(null)
    setSelectedTargetName(null)
    setAddTargetType(
      entityType === 'location' ? 'person' : entityType === 'person' ? 'location' : 'person'
    )
    setNature('')
    setNatureSearch('')
  }

  const handleAddSubmit = async () => {
    if (selectedTargetId == null || !nature.trim()) return
    const toType = addTargetType
    setSubmitting(true)
    try {
      if (entityType !== "location") {
        throw new Error("Connections can only be edited from canonical location detail in this build.")
      }
      await createConnectionForLocation(String(entityId), projectSlug, {
        to_entity_type: toType,
        to_entity_id: selectedTargetId,
        nature: nature.trim(),
      })
      setAddOpen(false)
      fetchConnections()
    } catch (e) {
      showError(e instanceof Error ? e.message : "Failed to create connection")
    } finally {
      setSubmitting(false)
    }
  }

  const handleEditOpen = (conn: Connection) => {
    setEditConnection(conn)
    setEditNature(conn.nature)
  }

  const handleEditSubmit = async () => {
    if (!editConnection) return
    setEditSubmitting(true)
    try {
      if (entityType !== "location") {
        throw new Error("Connections can only be edited from canonical location detail in this build.")
      }
      await updateConnectionForLocation(String(entityId), editConnection.id, projectSlug, {
        nature: editNature.trim(),
      })
      setEditConnection(null)
      fetchConnections()
    } catch (e) {
      showError(e instanceof Error ? e.message : "Failed to update connection")
    } finally {
      setEditSubmitting(false)
    }
  }

  const handleDeleteConfirm = async () => {
    if (!deleteConnection) return
    setDeleting(true)
    try {
      if (entityType !== "location") {
        throw new Error("Connections can only be edited from canonical location detail in this build.")
      }
      await deleteConnectionForLocation(String(entityId), deleteConnection.id, projectSlug)
      setDeleteConnection(null)
      fetchConnections()
    } catch (e) {
      showError(e instanceof Error ? e.message : "Failed to delete connection")
    } finally {
      setDeleting(false)
    }
  }

  const isFrom = (conn: Connection) =>
    conn.from_entity_type === entityType && String(conn.from_entity_id) === String(entityId)
  const otherDisplayName = (conn: Connection) =>
    isFrom(conn) ? conn.to_display_name : conn.from_display_name
  const otherType = (conn: Connection): EntityType =>
    (isFrom(conn) ? conn.to_entity_type : conn.from_entity_type) as EntityType
  const otherId = (conn: Connection) => (isFrom(conn) ? conn.to_entity_id : conn.from_entity_id)

  return (
    <>
      <Card>
        <CardHeader>
          <div className="flex flex-row items-start justify-between gap-4">
            <div className="space-y-1.5 min-w-0">
              <CardTitle>Connections</CardTitle>
              <CardDescription>
                Directed links between this {entityType} and other canonicals.
              </CardDescription>
            </div>
            <Button
              type="button"
              className="shrink-0"
              onClick={handleAddOpen}
              disabled={loading || entityType !== "location"}
            >
              <Plus className="h-4 w-4 mr-2" />
              Add connection
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {loading && <div className="text-center py-4">Loading connections...</div>}
          {error && (
            <div className="text-center py-4 text-destructive">{error}</div>
          )}
          {!loading && !error && (
            <Tabs defaultValue="list" className="w-full">
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
                {connections.length === 0 ? (
                  <div className="text-center py-4 text-muted-foreground">No connections yet.</div>
                ) : (
                  <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Direction</TableHead>
                  <TableHead>Nature</TableHead>
                  <TableHead>Other entity</TableHead>
                  <TableHead className="w-[120px]">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {connections.map((conn) => (
                  <TableRow key={conn.id}>
                    <TableCell>
                      {isFrom(conn) ? (
                        <>
                          <span className="font-medium">{entityDisplayName}</span>
                          <span className="mx-1">—</span>
                          <span className="text-muted-foreground">{conn.nature}</span>
                          <span className="mx-1">→</span>
                          <span>{conn.to_display_name}</span>
                        </>
                      ) : (
                        <>
                          <span>{conn.from_display_name}</span>
                          <span className="mx-1">—</span>
                          <span className="text-muted-foreground">{conn.nature}</span>
                          <span className="mx-1">→</span>
                          <span className="font-medium">{entityDisplayName}</span>
                        </>
                      )}
                    </TableCell>
                    <TableCell>{conn.nature}</TableCell>
                    <TableCell>
                      <a
                        href={getDetailUrl(otherType(conn), otherId(conn), projectSlug)}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-primary hover:underline inline-flex items-center gap-1"
                      >
                        {otherDisplayName(conn)}
                        <ExternalLink className="h-3 w-3" />
                      </a>
                    </TableCell>
                    <TableCell>
                      <div className="flex gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleEditOpen(conn)}
                          title="Edit nature"
                        >
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="destructive"
                          size="sm"
                          onClick={() => setDeleteConnection(conn)}
                          title="Delete connection"
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
                )}
              </TabsContent>
              <TabsContent value="graph" className="mt-4">
                <ConnectionsGraph
                  entityType={entityType}
                  entityId={entityId}
                  projectSlug={projectSlug}
                  entityDisplayName={entityDisplayName}
                  connections={connections}
                />
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
                  <Button
                    type="button"
                    variant={addTargetType === 'work' ? 'default' : 'outline'}
                    size="sm"
                    onClick={() => {
                      setAddTargetType('work')
                      setSelectedTargetId(null)
                      setSelectedTargetName(null)
                    }}
                  >
                    Work
                  </Button>
                </div>
              </div>
              <Label>
                {addTargetType === 'person'
                  ? 'Person'
                  : addTargetType === 'location'
                    ? 'Location'
                    : addTargetType === 'organization'
                      ? 'Organization'
                      : 'Work'}
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
                  projectSlug={projectSlug}
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
                  projectSlug={projectSlug}
                  excludeIds={entityType === 'organization' ? [entityId] : undefined}
                  onSelect={(id, displayName) => {
                    setSelectedTargetId(id)
                    setSelectorOpen(false)
                    setSelectedTargetName(displayName ?? `Organization #${id}`)
                  }}
                />
              ) : addTargetType === 'work' ? (
                <WorkSelector
                  open={selectorOpen}
                  onOpenChange={setSelectorOpen}
                  projectSlug={projectSlug}
                  excludeIds={entityType === 'work' ? [entityId] : undefined}
                  onSelect={(id, displayName) => {
                    setSelectedTargetId(id)
                    setSelectorOpen(false)
                    setSelectedTargetName(displayName ?? `Work #${id}`)
                  }}
                />
              ) : (
                <LocationSelector
                  open={selectorOpen}
                  onOpenChange={setSelectorOpen}
                  projectSlug={projectSlug}
                  excludeIds={entityType === 'location' ? [entityId] : undefined}
                  onSelect={(id, displayName) => {
                    setSelectedTargetId(id)
                    setSelectorOpen(false)
                    setSelectedTargetName(displayName ?? `Location #${id}`)
                  }}
                />
              )}
            </div>
            <NatureAutocomplete
              label="Nature of connection"
              value={nature}
              onChange={setNature}
              onSearchChange={setNatureSearch}
              suggestions={natureSuggestions}
              placeholder="e.g. mayor, born in"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAddOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleAddSubmit}
              disabled={selectedTargetId == null || !nature.trim() || submitting}
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
            <DialogDescription>Change the nature of this connection.</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <NatureAutocomplete
              label="Nature"
              value={editNature}
              onChange={setEditNature}
              suggestions={editNatureSuggestions}
              placeholder="e.g. mayor, born in"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditConnection(null)}>
              Cancel
            </Button>
            <Button onClick={handleEditSubmit} disabled={!editNature.trim() || editSubmitting}>
              {editSubmitting ? 'Saving...' : 'Save'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete confirmation */}
      <Dialog open={!!deleteConnection} onOpenChange={(open) => !open && setDeleteConnection(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete connection</DialogTitle>
            <DialogDescription>
              Remove the connection &quot;{entityDisplayName}&quot; — {deleteConnection?.nature} — &quot;
              {deleteConnection && otherDisplayName(deleteConnection)}&quot;? This cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteConnection(null)} disabled={deleting}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={handleDeleteConfirm} disabled={deleting}>
              {deleting ? 'Deleting...' : 'Delete'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
