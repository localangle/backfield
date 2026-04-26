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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Edit, Save, X, Loader2, Trash2, Plus, Code2, Table2 } from "lucide-react"
import {
  emptyKeyValueRows,
  flatRecordToRows,
  isFlatScalarRecord,
  newKeyValueRow,
  rowsToFlatRecord,
  valueToCellString,
  type KeyValueRow,
  type ScalarJson,
} from "@/lib/metaDataHeuristic"

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

type EditorMode = "table" | "json"

interface PerItemEdit {
  jsonText: string
  jsonError: string | null
  metaType: string
  editorMode: EditorMode
  kvRows: KeyValueRow[]
  tableError: string | null
}

interface MetaTabProps {
  entityId: number | null
  projectSlug: string
  config: MetaTabConfig
  onMetaUpdated?: () => void
}

function MetaDataReadOnly({ data }: { data: unknown }) {
  if (isFlatScalarRecord(data)) {
    const keys = Object.keys(data).sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" }))
    if (keys.length === 0) {
      return <p className="text-sm text-muted-foreground">Empty object</p>
    }
    return (
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-[40%]">Key</TableHead>
            <TableHead>Value</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {keys.map((k) => (
            <TableRow key={k}>
              <TableCell className="font-medium align-top">{k}</TableCell>
              <TableCell className="text-muted-foreground align-top font-mono text-sm">
                {valueToCellString(data[k] as ScalarJson)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    )
  }
  return (
    <pre className="bg-muted p-4 rounded-md overflow-x-auto text-sm">{JSON.stringify(data, null, 2)}</pre>
  )
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
  const [createEditorMode, setCreateEditorMode] = useState<EditorMode>("table")
  const [createKvRows, setCreateKvRows] = useState<KeyValueRow[]>(() => emptyKeyValueRows())
  const [createJsonText, setCreateJsonText] = useState("{}")
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

  const handleStartEdit = useCallback((metaItem: MetaItem) => {
    const data = metaItem.data
    let jsonText: string
    try {
      jsonText = JSON.stringify(data, null, 2)
    } catch {
      setEditingMeta((prev) => ({
        ...prev,
        [metaItem.id]: {
          jsonText: String(data),
          jsonError: "Failed to serialize JSON",
          metaType: metaItem.meta_type,
          editorMode: "json",
          kvRows: emptyKeyValueRows(),
          tableError: null,
        },
      }))
      return
    }

    const useTable = isFlatScalarRecord(data)
    setEditingMeta((prev) => ({
      ...prev,
      [metaItem.id]: {
        jsonText,
        jsonError: null,
        metaType: metaItem.meta_type,
        editorMode: useTable ? "table" : "json",
        kvRows: useTable ? flatRecordToRows(data) : emptyKeyValueRows(),
        tableError: null,
      },
    }))
  }, [])

  const handleCancelEdit = useCallback((metaId: number) => {
    setEditingMeta((prev) => {
      const newState = { ...prev }
      delete newState[metaId]
      return newState
    })
  }, [])

  const setEditToJsonMode = useCallback((metaId: number) => {
    setEditingMeta((prev) => {
      const cur = prev[metaId]
      if (!cur) return prev
      if (cur.editorMode === "json") {
        return prev
      }
      const built = rowsToFlatRecord(cur.kvRows)
      if (!built.ok) {
        return {
          ...prev,
          [metaId]: { ...cur, tableError: built.error },
        }
      }
      return {
        ...prev,
        [metaId]: {
          ...cur,
          editorMode: "json",
          jsonText: JSON.stringify(built.data, null, 2),
          jsonError: null,
          tableError: null,
        },
      }
    })
  }, [])

  const setEditToTableMode = useCallback((metaId: number) => {
    setEditingMeta((prev) => {
      const cur = prev[metaId]
      if (!cur) return prev
      if (cur.editorMode === "table") {
        return prev
      }
      const validation = validateJSON(cur.jsonText)
      if (!validation.valid) {
        return {
          ...prev,
          [metaId]: { ...cur, jsonError: validation.error || "Invalid JSON" },
        }
      }
      if (!isFlatScalarRecord(validation.data)) {
        return {
          ...prev,
          [metaId]: {
            ...cur,
            jsonError: "Only flat key/value objects (string keys, scalar values) can use table view.",
          },
        }
      }
      return {
        ...prev,
        [metaId]: {
          ...cur,
          editorMode: "table",
          kvRows: flatRecordToRows(validation.data),
          jsonError: null,
          tableError: null,
        },
      }
    })
  }, [validateJSON])

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
            tableError: null,
          },
        }))
        return
      }

      let payload: unknown
      if (editState.editorMode === "table") {
        const built = rowsToFlatRecord(editState.kvRows)
        if (!built.ok) {
          setEditingMeta((prev) => ({
            ...prev,
            [metaItem.id]: { ...prev[metaItem.id], tableError: built.error, jsonError: null },
          }))
          return
        }
        payload = built.data
      } else {
        const validation = validateJSON(editState.jsonText)
        if (!validation.valid) {
          setEditingMeta((prev) => ({
            ...prev,
            [metaItem.id]: {
              ...prev[metaItem.id],
              jsonError: validation.error || "Invalid JSON",
              tableError: null,
            },
          }))
          return
        }
        payload = validation.data
      }

      try {
        setSaving((prev) => ({ ...prev, [metaItem.id]: true }))
        await config.api.updateMeta(entityId, metaItem.id, projectSlug, {
          data: payload,
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
            tableError: null,
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

  const openCreateDialog = useCallback(() => {
    setNewMetaType("")
    setCreateEditorMode("table")
    setCreateKvRows(emptyKeyValueRows())
    setCreateJsonText("{}")
    setCreateError(null)
    setShowCreateDialog(true)
  }, [])

  const handleCreate = useCallback(async () => {
    if (!entityId || !newMetaType.trim()) return

    let data: unknown
    if (createEditorMode === "table") {
      const built = rowsToFlatRecord(createKvRows)
      if (!built.ok) {
        setCreateError(built.error)
        return
      }
      data = built.data
    } else {
      const validation = validateJSON(createJsonText.trim() || "{}")
      if (!validation.valid) {
        setCreateError(validation.error || "Invalid JSON")
        return
      }
      data = validation.data
    }

    try {
      setCreating(true)
      setCreateError(null)
      await config.api.createMeta(entityId, projectSlug, {
        meta_type: newMetaType.trim(),
        data,
      })
      await loadMeta()
      setShowCreateDialog(false)
      onMetaUpdated?.()
    } catch (error) {
      console.error("Failed to create meta:", error)
      setCreateError(error instanceof Error ? error.message : "Failed to create")
    } finally {
      setCreating(false)
    }
  }, [
    entityId,
    projectSlug,
    newMetaType,
    createEditorMode,
    createKvRows,
    createJsonText,
    config,
    validateJSON,
    loadMeta,
    onMetaUpdated,
  ])

  const switchCreateToJson = useCallback(() => {
    if (createEditorMode === "json") return
    const built = rowsToFlatRecord(createKvRows)
    if (!built.ok) {
      setCreateError(built.error)
      return
    }
    setCreateJsonText(JSON.stringify(built.data, null, 2))
    setCreateEditorMode("json")
    setCreateError(null)
  }, [createEditorMode, createKvRows])

  const switchCreateToTable = useCallback(() => {
    if (createEditorMode === "table") return
    const validation = validateJSON(createJsonText.trim() || "{}")
    if (!validation.valid) {
      setCreateError(validation.error || "Invalid JSON")
      return
    }
    if (!isFlatScalarRecord(validation.data)) {
      setCreateError("Only flat key/value objects can use table view. Edit JSON to simplify, or stay in JSON mode.")
      return
    }
    setCreateKvRows(flatRecordToRows(validation.data))
    setCreateEditorMode("table")
    setCreateError(null)
  }, [createEditorMode, createJsonText, validateJSON])

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
            <Button type="button" className="shrink-0" onClick={openCreateDialog} disabled={!entityId || loading}>
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
                                      tableError: null,
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
                          <div className="flex shrink-0 flex-wrap gap-2">
                            <Button
                              size="sm"
                              onClick={() => void handleSaveEdit(item)}
                              disabled={saving[item.id]}
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
                    <CardContent className="space-y-3">
                      {isEditing ? (
                        <div className="space-y-3">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                              Data
                            </span>
                            <div className="flex rounded-md border border-border p-0.5">
                              <Button
                                type="button"
                                variant={editState.editorMode === "table" ? "secondary" : "ghost"}
                                size="sm"
                                className="h-8 px-2"
                                onClick={() => setEditToTableMode(item.id)}
                              >
                                <Table2 className="h-4 w-4 mr-1.5" />
                                Table
                              </Button>
                              <Button
                                type="button"
                                variant={editState.editorMode === "json" ? "secondary" : "ghost"}
                                size="sm"
                                className="h-8 px-2"
                                onClick={() => setEditToJsonMode(item.id)}
                              >
                                <Code2 className="h-4 w-4 mr-1.5" />
                                JSON
                              </Button>
                            </div>
                          </div>
                          {editState.editorMode === "table" ? (
                            <div className="space-y-2">
                              <Table>
                                <TableHeader>
                                  <TableRow>
                                    <TableHead className="w-[38%]">Key</TableHead>
                                    <TableHead>Value</TableHead>
                                    <TableHead className="w-[52px] text-right"> </TableHead>
                                  </TableRow>
                                </TableHeader>
                                <TableBody>
                                  {editState.kvRows.map((row) => (
                                    <TableRow key={row.id}>
                                      <TableCell>
                                        <Input
                                          value={row.key}
                                          onChange={(e) => {
                                            const v = e.target.value
                                            setEditingMeta((prev) => ({
                                              ...prev,
                                              [item.id]: {
                                                ...prev[item.id],
                                                kvRows: prev[item.id].kvRows.map((r) =>
                                                  r.id === row.id ? { ...r, key: v } : r,
                                                ),
                                                tableError: null,
                                              },
                                            }))
                                          }}
                                          placeholder="e.g. Party"
                                          className="h-9"
                                        />
                                      </TableCell>
                                      <TableCell>
                                        <Input
                                          value={row.valueStr}
                                          onChange={(e) => {
                                            const v = e.target.value
                                            setEditingMeta((prev) => ({
                                              ...prev,
                                              [item.id]: {
                                                ...prev[item.id],
                                                kvRows: prev[item.id].kvRows.map((r) =>
                                                  r.id === row.id ? { ...r, valueStr: v } : r,
                                                ),
                                                tableError: null,
                                              },
                                            }))
                                          }}
                                          placeholder='e.g. Democrat or 1000 or "quoted"'
                                          className="h-9 font-mono text-sm"
                                        />
                                      </TableCell>
                                      <TableCell className="text-right">
                                        <Button
                                          type="button"
                                          variant="ghost"
                                          size="icon"
                                          className="h-8 w-8 shrink-0"
                                          disabled={editState.kvRows.length <= 1}
                                          onClick={() =>
                                            setEditingMeta((prev) => ({
                                              ...prev,
                                              [item.id]: {
                                                ...prev[item.id],
                                                kvRows: prev[item.id].kvRows.filter((r) => r.id !== row.id),
                                                tableError: null,
                                              },
                                            }))
                                          }
                                          aria-label="Remove row"
                                        >
                                          <Trash2 className="h-4 w-4" />
                                        </Button>
                                      </TableCell>
                                    </TableRow>
                                  ))}
                                </TableBody>
                              </Table>
                              <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                onClick={() =>
                                  setEditingMeta((prev) => {
                                    const cur = prev[item.id]
                                    if (!cur) return prev
                                    return {
                                      ...prev,
                                      [item.id]: {
                                        ...cur,
                                        kvRows: [...cur.kvRows, newKeyValueRow()],
                                        tableError: null,
                                      },
                                    }
                                  })
                                }
                              >
                                <Plus className="h-4 w-4 mr-2" />
                                Add row
                              </Button>
                              <p className="text-xs text-muted-foreground">
                                Values can be plain text, or JSON literals for numbers and booleans (
                                <code className="text-xs">42</code>, <code className="text-xs">true</code>,{" "}
                                <code className="text-xs">null</code>, <code className="text-xs">{`"text"`}</code>
                                ). Use JSON mode for nested structures.
                              </p>
                              {editState.tableError && (
                                <p className="text-sm text-destructive">{editState.tableError}</p>
                              )}
                            </div>
                          ) : (
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
                                className={`font-mono text-sm ${editState.jsonError ? "border-destructive" : ""}`}
                                rows={12}
                              />
                              {editState.jsonError && (
                                <p className="text-sm text-destructive mt-2">{editState.jsonError}</p>
                              )}
                            </div>
                          )}
                        </div>
                      ) : (
                        <MetaDataReadOnly data={item.data} />
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
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Add Metadata</DialogTitle>
            <DialogDescription>
              Add new metadata for this {config.displayName.singular.toLowerCase()}. Use the table for simple
              fields, or JSON for nested data.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>Meta type *</Label>
              <Input
                value={newMetaType}
                onChange={(e) => setNewMetaType(e.target.value)}
                placeholder="e.g., demographics, source, notes"
              />
            </div>
            <div className="space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                <Label className="text-sm">Data</Label>
                <div className="flex rounded-md border border-border p-0.5">
                  <Button
                    type="button"
                    variant={createEditorMode === "table" ? "secondary" : "ghost"}
                    size="sm"
                    className="h-8 px-2"
                    onClick={switchCreateToTable}
                  >
                    <Table2 className="h-4 w-4 mr-1.5" />
                    Table
                  </Button>
                  <Button
                    type="button"
                    variant={createEditorMode === "json" ? "secondary" : "ghost"}
                    size="sm"
                    className="h-8 px-2"
                    onClick={switchCreateToJson}
                  >
                    <Code2 className="h-4 w-4 mr-1.5" />
                    JSON
                  </Button>
                </div>
              </div>
              {createEditorMode === "table" ? (
                <div className="space-y-2">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="w-[38%]">Key</TableHead>
                        <TableHead>Value</TableHead>
                        <TableHead className="w-[52px] text-right"> </TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {createKvRows.map((row) => (
                        <TableRow key={row.id}>
                          <TableCell>
                            <Input
                              value={row.key}
                              onChange={(e) => {
                                const v = e.target.value
                                setCreateKvRows((rows) => rows.map((r) => (r.id === row.id ? { ...r, key: v } : r)))
                                setCreateError(null)
                              }}
                              placeholder="Key"
                              className="h-9"
                            />
                          </TableCell>
                          <TableCell>
                            <Input
                              value={row.valueStr}
                              onChange={(e) => {
                                const v = e.target.value
                                setCreateKvRows((rows) => rows.map((r) => (r.id === row.id ? { ...r, valueStr: v } : r)))
                                setCreateError(null)
                              }}
                              placeholder="Value"
                              className="h-9 font-mono text-sm"
                            />
                          </TableCell>
                          <TableCell className="text-right">
                            <Button
                              type="button"
                              variant="ghost"
                              size="icon"
                              className="h-8 w-8"
                              disabled={createKvRows.length <= 1}
                              onClick={() => setCreateKvRows((rows) => rows.filter((r) => r.id !== row.id))}
                              aria-label="Remove row"
                            >
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => setCreateKvRows((rows) => [...rows, newKeyValueRow()])}
                  >
                    <Plus className="h-4 w-4 mr-2" />
                    Add row
                  </Button>
                </div>
              ) : (
                <Textarea
                  value={createJsonText}
                  onChange={(e) => {
                    setCreateJsonText(e.target.value)
                    setCreateError(null)
                  }}
                  placeholder="{}"
                  rows={10}
                  className="font-mono text-sm"
                />
              )}
              {createError && <p className="text-sm text-destructive">{createError}</p>}
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
