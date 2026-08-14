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
import { Edit, Save, X, Loader2, Trash2, Plus } from "lucide-react"
import {
  formatMetaValue,
  isValidMetaTypeSlug,
  normalizeMetaTypeSlug,
  parseMetaValueInput,
  type MetaValueType,
} from "@/lib/metaDataHeuristic"
import type { CanonicalMetaWriteBody } from "@/lib/stylebook-api/meta"

export interface MetaItem {
  id: number
  meta_type: string
  value_type: MetaValueType
  value: string | number | boolean
  created_at?: string
}

export interface MetaResponse {
  meta: MetaItem[]
  count: number
}

export interface MetaTabConfig {
  type: string
  displayName: { singular: string; plural: string }
  /** When set, shown under the Metadata title after load instead of the meta-item count. */
  subtitle?: string
  api: {
    getMeta: (entityId: string | number, projectSlug: string) => Promise<MetaResponse>
    createMeta: (
      entityId: string | number,
      projectSlug: string,
      data: CanonicalMetaWriteBody,
    ) => Promise<unknown>
    updateMeta: (
      entityId: string | number,
      metaId: number,
      projectSlug: string,
      data: CanonicalMetaWriteBody,
    ) => Promise<unknown>
    deleteMeta: (entityId: string | number, metaId: number, projectSlug: string) => Promise<unknown>
  }
}

interface PerItemEdit {
  metaType: string
  valueType: MetaValueType
  valueText: string
  error: string | null
}

interface MetaTabProps {
  entityId: string | number | null
  projectSlug: string
  config: MetaTabConfig
  onMetaUpdated?: () => void
}

const VALUE_TYPE_OPTIONS: { value: MetaValueType; label: string }[] = [
  { value: "text", label: "Text" },
  { value: "number", label: "Number" },
  { value: "boolean", label: "Yes / no" },
]

function valueToEditorText(valueType: MetaValueType, value: string | number | boolean): string {
  if (valueType === "boolean") return value ? "true" : "false"
  return String(value)
}

export default function MetaTab({ entityId, projectSlug, config, onMetaUpdated }: MetaTabProps) {
  const [meta, setMeta] = useState<MetaResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [editingMeta, setEditingMeta] = useState<Record<number, PerItemEdit>>({})
  const [saving, setSaving] = useState<Record<number, boolean>>({})
  const [deleting, setDeleting] = useState<Record<number, boolean>>({})
  const [showDeleteDialog, setShowDeleteDialog] = useState(false)
  const [metaToDelete, setMetaToDelete] = useState<MetaItem | null>(null)
  const [showCreateDialog, setShowCreateDialog] = useState(false)
  const [newMetaType, setNewMetaType] = useState("")
  const [newValueType, setNewValueType] = useState<MetaValueType>("text")
  const [newValueText, setNewValueText] = useState("")
  const [createError, setCreateError] = useState<string | null>(null)
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
    setEditingMeta((prev) => ({
      ...prev,
      [metaItem.id]: {
        metaType: metaItem.meta_type,
        valueType: metaItem.value_type,
        valueText: valueToEditorText(metaItem.value_type, metaItem.value),
        error: null,
      },
    }))
  }, [])

  const handleCancelEdit = useCallback((metaId: number) => {
    setEditingMeta((prev) => {
      const next = { ...prev }
      delete next[metaId]
      return next
    })
  }, [])

  const handleSaveEdit = useCallback(
    async (metaItem: MetaItem) => {
      if (!entityId) return
      const edit = editingMeta[metaItem.id]
      if (!edit) return

      if (!isValidMetaTypeSlug(edit.metaType)) {
        setEditingMeta((prev) => ({
          ...prev,
          [metaItem.id]: {
            ...edit,
            error: "Use a short key with lowercase letters, numbers, and underscores.",
          },
        }))
        return
      }
      const parsed = parseMetaValueInput(edit.valueType, edit.valueText)
      if (!parsed.ok) {
        setEditingMeta((prev) => ({
          ...prev,
          [metaItem.id]: { ...edit, error: parsed.error },
        }))
        return
      }

      try {
        setSaving((prev) => ({ ...prev, [metaItem.id]: true }))
        await config.api.updateMeta(entityId, metaItem.id, projectSlug, {
          meta_type: normalizeMetaTypeSlug(edit.metaType),
          value_type: edit.valueType,
          value: parsed.value,
        })
        handleCancelEdit(metaItem.id)
        await loadMeta()
        onMetaUpdated?.()
      } catch (error) {
        console.error("Failed to update meta:", error)
        setEditingMeta((prev) => ({
          ...prev,
          [metaItem.id]: {
            ...edit,
            error: error instanceof Error ? error.message : "Could not save this detail.",
          },
        }))
      } finally {
        setSaving((prev) => ({ ...prev, [metaItem.id]: false }))
      }
    },
    [entityId, projectSlug, config, editingMeta, handleCancelEdit, loadMeta, onMetaUpdated],
  )

  const handleCreate = useCallback(async () => {
    if (!entityId) return
    if (!isValidMetaTypeSlug(newMetaType)) {
      setCreateError("Use a short key with lowercase letters, numbers, and underscores.")
      return
    }
    const parsed = parseMetaValueInput(newValueType, newValueText)
    if (!parsed.ok) {
      setCreateError(parsed.error)
      return
    }
    try {
      setCreating(true)
      setCreateError(null)
      await config.api.createMeta(entityId, projectSlug, {
        meta_type: normalizeMetaTypeSlug(newMetaType),
        value_type: newValueType,
        value: parsed.value,
      })
      setShowCreateDialog(false)
      setNewMetaType("")
      setNewValueType("text")
      setNewValueText("")
      await loadMeta()
      onMetaUpdated?.()
    } catch (error) {
      console.error("Failed to create meta:", error)
      setCreateError(error instanceof Error ? error.message : "Could not add this detail.")
    } finally {
      setCreating(false)
    }
  }, [
    entityId,
    projectSlug,
    config,
    newMetaType,
    newValueType,
    newValueText,
    loadMeta,
    onMetaUpdated,
  ])

  const confirmDelete = useCallback(async () => {
    if (!entityId || !metaToDelete) return
    try {
      setDeleting((prev) => ({ ...prev, [metaToDelete.id]: true }))
      await config.api.deleteMeta(entityId, metaToDelete.id, projectSlug)
      setShowDeleteDialog(false)
      setMetaToDelete(null)
      await loadMeta()
      onMetaUpdated?.()
    } catch (error) {
      console.error("Failed to delete meta:", error)
    } finally {
      setDeleting((prev) => ({ ...prev, [metaToDelete.id]: false }))
    }
  }, [entityId, metaToDelete, projectSlug, config, loadMeta, onMetaUpdated])

  if (!entityId) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Details</CardTitle>
          <CardDescription>Save this record before adding details.</CardDescription>
        </CardHeader>
      </Card>
    )
  }

  if (loading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Details</CardTitle>
        </CardHeader>
        <CardContent className="flex items-center gap-2 text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading…
        </CardContent>
      </Card>
    )
  }

  const items = meta?.meta ?? []

  return (
    <>
      <Card>
        <CardHeader className="flex flex-row items-start justify-between gap-4">
          <div>
            <CardTitle>Details</CardTitle>
            <CardDescription>
              {config.subtitle ??
                (items.length === 1
                  ? "1 detail"
                  : `${items.length} details`)}
            </CardDescription>
          </div>
          <Button
            type="button"
            size="sm"
            onClick={() => {
              setCreateError(null)
              setShowCreateDialog(true)
            }}
          >
            <Plus className="h-4 w-4 mr-1" />
            Add detail
          </Button>
        </CardHeader>
        <CardContent className="space-y-4">
          {items.length === 0 ? (
            <p className="text-sm text-muted-foreground">No extra details yet.</p>
          ) : (
            items.map((item) => {
              const edit = editingMeta[item.id]
              const isEditing = Boolean(edit)
              return (
                <div key={item.id} className="rounded-md border p-4 space-y-3">
                  {isEditing && edit ? (
                    <>
                      <div className="grid gap-3 sm:grid-cols-3">
                        <div className="space-y-1">
                          <Label htmlFor={`meta-type-${item.id}`}>Key</Label>
                          <Input
                            id={`meta-type-${item.id}`}
                            value={edit.metaType}
                            onChange={(e) =>
                              setEditingMeta((prev) => ({
                                ...prev,
                                [item.id]: {
                                  ...edit,
                                  metaType: e.target.value,
                                  error: null,
                                },
                              }))
                            }
                          />
                        </div>
                        <div className="space-y-1">
                          <Label htmlFor={`meta-vt-${item.id}`}>Type</Label>
                          <select
                            id={`meta-vt-${item.id}`}
                            className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm"
                            value={edit.valueType}
                            onChange={(e) =>
                              setEditingMeta((prev) => ({
                                ...prev,
                                [item.id]: {
                                  ...edit,
                                  valueType: e.target.value as MetaValueType,
                                  valueText:
                                    e.target.value === "boolean" ? "true" : edit.valueText,
                                  error: null,
                                },
                              }))
                            }
                          >
                            {VALUE_TYPE_OPTIONS.map((opt) => (
                              <option key={opt.value} value={opt.value}>
                                {opt.label}
                              </option>
                            ))}
                          </select>
                        </div>
                        <div className="space-y-1">
                          <Label htmlFor={`meta-val-${item.id}`}>Value</Label>
                          {edit.valueType === "boolean" ? (
                            <select
                              id={`meta-val-${item.id}`}
                              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm"
                              value={edit.valueText}
                              onChange={(e) =>
                                setEditingMeta((prev) => ({
                                  ...prev,
                                  [item.id]: {
                                    ...edit,
                                    valueText: e.target.value,
                                    error: null,
                                  },
                                }))
                              }
                            >
                              <option value="true">Yes</option>
                              <option value="false">No</option>
                            </select>
                          ) : (
                            <Input
                              id={`meta-val-${item.id}`}
                              type={edit.valueType === "number" ? "number" : "text"}
                              value={edit.valueText}
                              onChange={(e) =>
                                setEditingMeta((prev) => ({
                                  ...prev,
                                  [item.id]: {
                                    ...edit,
                                    valueText: e.target.value,
                                    error: null,
                                  },
                                }))
                              }
                            />
                          )}
                        </div>
                      </div>
                      {edit.error ? (
                        <p className="text-sm text-destructive">{edit.error}</p>
                      ) : null}
                      <div className="flex gap-2">
                        <Button
                          type="button"
                          size="sm"
                          disabled={saving[item.id]}
                          onClick={() => void handleSaveEdit(item)}
                        >
                          {saving[item.id] ? (
                            <Loader2 className="h-4 w-4 animate-spin mr-1" />
                          ) : (
                            <Save className="h-4 w-4 mr-1" />
                          )}
                          Save
                        </Button>
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          onClick={() => handleCancelEdit(item.id)}
                        >
                          <X className="h-4 w-4 mr-1" />
                          Cancel
                        </Button>
                      </div>
                    </>
                  ) : (
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <div className="font-medium">{item.meta_type}</div>
                        <div className="text-sm text-muted-foreground">
                          {VALUE_TYPE_OPTIONS.find((o) => o.value === item.value_type)?.label ??
                            item.value_type}
                          {" · "}
                          {formatMetaValue(item.value)}
                        </div>
                      </div>
                      <div className="flex gap-2">
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          onClick={() => handleStartEdit(item)}
                        >
                          <Edit className="h-4 w-4" />
                        </Button>
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          disabled={deleting[item.id]}
                          onClick={() => {
                            setMetaToDelete(item)
                            setShowDeleteDialog(true)
                          }}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                  )}
                </div>
              )
            })
          )}
        </CardContent>
      </Card>

      <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add detail</DialogTitle>
            <DialogDescription>
              Give this a short key, choose a type, and enter a value.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-3">
            <div className="space-y-1">
              <Label htmlFor="new-meta-type">Key</Label>
              <Input
                id="new-meta-type"
                placeholder="population"
                value={newMetaType}
                onChange={(e) => {
                  setNewMetaType(e.target.value)
                  setCreateError(null)
                }}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="new-meta-vt">Type</Label>
              <select
                id="new-meta-vt"
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm"
                value={newValueType}
                onChange={(e) => {
                  const next = e.target.value as MetaValueType
                  setNewValueType(next)
                  setNewValueText(next === "boolean" ? "true" : "")
                  setCreateError(null)
                }}
              >
                {VALUE_TYPE_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="new-meta-val">Value</Label>
              {newValueType === "boolean" ? (
                <select
                  id="new-meta-val"
                  className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm"
                  value={newValueText || "true"}
                  onChange={(e) => {
                    setNewValueText(e.target.value)
                    setCreateError(null)
                  }}
                >
                  <option value="true">Yes</option>
                  <option value="false">No</option>
                </select>
              ) : (
                <Input
                  id="new-meta-val"
                  type={newValueType === "number" ? "number" : "text"}
                  value={newValueText}
                  onChange={(e) => {
                    setNewValueText(e.target.value)
                    setCreateError(null)
                  }}
                />
              )}
            </div>
            {createError ? <p className="text-sm text-destructive">{createError}</p> : null}
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setShowCreateDialog(false)}>
              Cancel
            </Button>
            <Button type="button" disabled={creating} onClick={() => void handleCreate()}>
              {creating ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : null}
              Add
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Remove detail?</DialogTitle>
            <DialogDescription>
              This removes “{metaToDelete?.meta_type}” from the record.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setShowDeleteDialog(false)}>
              Cancel
            </Button>
            <Button type="button" variant="destructive" onClick={() => void confirmDelete()}>
              Remove
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
