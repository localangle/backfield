import React, { useCallback, useEffect, useState } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Edit, Save, X, Loader2, Trash2, Plus } from "lucide-react"

export interface MetaItem {
  id: number
  meta_type: string
  data: unknown
  created_at?: string
  updated_at?: string
}

export interface MetaResponse {
  meta: MetaItem[]
  count: number
  location_id?: number
}

export interface MetaTabConfig {
  type: string
  displayName: { singular: string; plural: string }
  api: {
    getMeta: (entityId: number, projectSlug: string) => Promise<MetaResponse>
    createMeta: (
      entityId: number,
      projectSlug: string,
      data: { meta_type: string; data: unknown },
    ) => Promise<unknown>
    updateMeta: (
      entityId: number,
      metaId: number,
      projectSlug: string,
      data: { data: unknown; meta_type?: string },
    ) => Promise<unknown>
    deleteMeta: (entityId: number, metaId: number, projectSlug: string) => Promise<unknown>
  }
}

interface MetaTabProps {
  entityId: number | null
  projectSlug: string
  config: MetaTabConfig
  onMetaUpdated?: () => void
}

export default function MetaTab({ entityId, projectSlug, config, onMetaUpdated }: MetaTabProps) {
  const [meta, setMeta] = useState<MetaResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [editingMeta, setEditingMeta] = useState<
    Record<number, { jsonText: string; jsonError: string | null; metaType: string }>
  >({})
  const [saving, setSaving] = useState<Record<number, boolean>>({})
  const [deleting, setDeleting] = useState<Record<number, boolean>>({})
  const [showDeleteDialog, setShowDeleteDialog] = useState(false)
  const [metaToDelete, setMetaToDelete] = useState<MetaItem | null>(null)
  const [showCreateDialog, setShowCreateDialog] = useState(false)
  const [newMetaType, setNewMetaType] = useState("")
  const [newMetaData, setNewMetaData] = useState("")
  const [creating, setCreating] = useState(false)

  const loadMeta = useCallback(async () => {
    if (!entityId) {
      setLoading(false)
      setMeta(null)
      return
    }

    try {
      setLoading(true)
      const data = await config.api.getMeta(entityId, projectSlug)
      setMeta(data as MetaResponse)
    } catch (error) {
      console.error(`Failed to load ${config.type} meta:`, error)
      setMeta(null)
    } finally {
      setLoading(false)
    }
  }, [entityId, projectSlug, config])

  useEffect(() => {
    void loadMeta()
  }, [loadMeta])

  const handleStartEdit = useCallback((metaItem: MetaItem) => {
    try {
      const jsonText = JSON.stringify(metaItem.data, null, 2)
      setEditingMeta((prev) => ({
        ...prev,
        [metaItem.id]: {
          jsonText,
          jsonError: null,
          metaType: metaItem.meta_type,
        },
      }))
    } catch {
      setEditingMeta((prev) => ({
        ...prev,
        [metaItem.id]: {
          jsonText: String(metaItem.data),
          jsonError: "Failed to serialize JSON",
          metaType: metaItem.meta_type,
        },
      }))
    }
  }, [])

  const handleCancelEdit = useCallback((metaId: number) => {
    setEditingMeta((prev) => {
      const newState = { ...prev }
      delete newState[metaId]
      return newState
    })
  }, [])

  const validateJSON = useCallback((jsonText: string): { valid: boolean; data?: unknown; error?: string } => {
    try {
      const parsed: unknown = JSON.parse(jsonText)
      return { valid: true, data: parsed }
    } catch (error) {
      return {
        valid: false,
        error: error instanceof Error ? error.message : "Invalid JSON",
      }
    }
  }, [])

  const handleSaveEdit = useCallback(
    async (metaItem: MetaItem) => {
      if (!entityId) return

      const editState = editingMeta[metaItem.id]
      if (!editState) return

      const typeTrim = editState.metaType.trim()
      if (!typeTrim) {
        setEditingMeta((prev) => ({
          ...prev,
          [metaItem.id]: {
            ...prev[metaItem.id],
            jsonError: "Meta type is required",
          },
        }))
        return
      }

      const validation = validateJSON(editState.jsonText)
      if (!validation.valid) {
        setEditingMeta((prev) => ({
          ...prev,
          [metaItem.id]: {
            ...prev[metaItem.id],
            jsonError: validation.error || "Invalid JSON",
          },
        }))
        return
      }

      try {
        setSaving((prev) => ({ ...prev, [metaItem.id]: true }))
        await config.api.updateMeta(entityId, metaItem.id, projectSlug, {
          data: validation.data,
          meta_type: typeTrim,
        })
        await loadMeta()
        handleCancelEdit(metaItem.id)
        onMetaUpdated?.()
      } catch (error) {
        console.error("Failed to update meta:", error)
        setEditingMeta((prev) => ({
          ...prev,
          [metaItem.id]: {
            ...prev[metaItem.id],
            jsonError: error instanceof Error ? error.message : "Failed to update",
          },
        }))
      } finally {
        setSaving((prev) => {
          const newState = { ...prev }
          delete newState[metaItem.id]
          return newState
        })
      }
    },
    [entityId, projectSlug, editingMeta, config, validateJSON, loadMeta, handleCancelEdit, onMetaUpdated],
  )

  const handleDelete = useCallback((item: MetaItem) => {
    setMetaToDelete(item)
    setShowDeleteDialog(true)
  }, [])

  const confirmDelete = useCallback(async () => {
    if (!entityId || !metaToDelete) return

    try {
      setDeleting((prev) => ({ ...prev, [metaToDelete.id]: true }))
      await config.api.deleteMeta(entityId, metaToDelete.id, projectSlug)
      await loadMeta()
      onMetaUpdated?.()
    } catch (error) {
      console.error("Failed to delete meta:", error)
    } finally {
      setDeleting((prev) => {
        const newState = { ...prev }
        delete newState[metaToDelete.id]
        return newState
      })
      setShowDeleteDialog(false)
      setMetaToDelete(null)
    }
  }, [entityId, metaToDelete, projectSlug, config, loadMeta, onMetaUpdated])

  const handleCreate = useCallback(async () => {
    if (!entityId || !newMetaType.trim()) return

    const validation = validateJSON(newMetaData || "{}")
    if (!validation.valid) {
      return
    }

    try {
      setCreating(true)
      await config.api.createMeta(entityId, projectSlug, {
        meta_type: newMetaType.trim(),
        data: validation.data,
      })
      await loadMeta()
      setShowCreateDialog(false)
      setNewMetaType("")
      setNewMetaData("")
      onMetaUpdated?.()
    } catch (error) {
      console.error("Failed to create meta:", error)
    } finally {
      setCreating(false)
    }
  }, [entityId, projectSlug, newMetaType, newMetaData, config, validateJSON, loadMeta, onMetaUpdated])

  const description =
    loading || !meta
      ? loading
        ? "Loading…"
        : "Could not load metadata."
      : `${meta.count} meta item${meta.count !== 1 ? "s" : ""} for this ${config.displayName.singular.toLowerCase()}`

  return (
    <>
      <Card>
        <CardHeader>
          <div className="flex flex-row items-start justify-between gap-4">
            <div className="space-y-1.5 min-w-0">
              <CardTitle>Metadata</CardTitle>
              <CardDescription>{description}</CardDescription>
            </div>
            <Button
              type="button"
              className="shrink-0"
              onClick={() => setShowCreateDialog(true)}
              disabled={!entityId || loading}
            >
              <Plus className="h-4 w-4 mr-2" />
              Add Meta
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="py-8 text-center">
              <Loader2 className="h-6 w-6 animate-spin mx-auto mb-2" />
              <p className="text-muted-foreground">Loading meta…</p>
            </div>
          ) : !meta ? (
            <div className="py-6 text-center text-muted-foreground">No metadata available.</div>
          ) : meta.meta.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              No metadata yet. Use Add Meta to create an entry.
            </div>
          ) : (
            <div className="space-y-4">
              {meta.meta.map((item) => {
                const isEditing = editingMeta[item.id] !== undefined
                const editState = editingMeta[item.id]

                return (
                  <Card key={item.id}>
                    <CardHeader className="pb-3">
                      <div className="flex items-center justify-between gap-2">
                        <div className="min-w-0">
                          {!isEditing ? (
                            <CardTitle className="text-base">{item.meta_type}</CardTitle>
                          ) : (
                            <div className="space-y-1">
                              <Label className="text-xs text-muted-foreground">Meta type</Label>
                              <Input
                                value={editState.metaType}
                                onChange={(e) =>
                                  setEditingMeta((prev) => ({
                                    ...prev,
                                    [item.id]: {
                                      ...prev[item.id],
                                      metaType: e.target.value,
                                      jsonError: null,
                                    },
                                  }))
                                }
                                className="max-w-md font-medium"
                              />
                            </div>
                          )}
                        </div>
                        {!isEditing ? (
                          <div className="flex shrink-0 gap-2">
                            <Button variant="outline" size="sm" onClick={() => handleStartEdit(item)}>
                              <Edit className="h-4 w-4 mr-2" />
                              Edit
                            </Button>
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => handleDelete(item)}
                              disabled={deleting[item.id]}
                            >
                              {deleting[item.id] ? (
                                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                              ) : (
                                <Trash2 className="h-4 w-4 mr-2" />
                              )}
                              Delete
                            </Button>
                          </div>
                        ) : (
                          <div className="flex shrink-0 gap-2">
                            <Button
                              size="sm"
                              onClick={() => void handleSaveEdit(item)}
                              disabled={saving[item.id] || !!editState?.jsonError}
                            >
                              {saving[item.id] ? (
                                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                              ) : (
                                <Save className="h-4 w-4 mr-2" />
                              )}
                              Save
                            </Button>
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => handleCancelEdit(item.id)}
                              disabled={saving[item.id]}
                            >
                              <X className="h-4 w-4 mr-2" />
                              Cancel
                            </Button>
                          </div>
                        )}
                      </div>
                    </CardHeader>
                    <CardContent>
                      {isEditing ? (
                        <div>
                          <Textarea
                            value={editState.jsonText}
                            onChange={(e) => {
                              setEditingMeta((prev) => ({
                                ...prev,
                                [item.id]: {
                                  ...prev[item.id],
                                  jsonText: e.target.value,
                                  jsonError: null,
                                },
                              }))
                            }}
                            className={`font-mono text-sm ${editState.jsonError ? "border-red-500" : ""}`}
                            rows={10}
                          />
                          {editState.jsonError && (
                            <p className="text-sm text-red-500 mt-2">{editState.jsonError}</p>
                          )}
                        </div>
                      ) : (
                        <pre className="bg-muted p-4 rounded-md overflow-x-auto text-sm">
                          {JSON.stringify(item.data, null, 2)}
                        </pre>
                      )}
                    </CardContent>
                  </Card>
                )
              })}
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add Metadata</DialogTitle>
            <DialogDescription>
              Add new metadata for this {config.displayName.singular.toLowerCase()}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>Meta type *</Label>
              <Input
                value={newMetaType}
                onChange={(e) => setNewMetaType(e.target.value)}
                placeholder="e.g., source, notes, etc."
              />
            </div>
            <div>
              <Label>Data (JSON) *</Label>
              <Textarea
                value={newMetaData}
                onChange={(e) => setNewMetaData(e.target.value)}
                placeholder='{"key": "value"}'
                rows={8}
                className="font-mono text-sm"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCreateDialog(false)}>
              Cancel
            </Button>
            <Button onClick={() => void handleCreate()} disabled={creating || !newMetaType.trim()}>
              {creating ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <Plus className="h-4 w-4 mr-2" />
              )}
              Create
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Metadata</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete this metadata? This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowDeleteDialog(false)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={() => void confirmDelete()}>
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
