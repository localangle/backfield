import { useCallback, useEffect, useMemo, useState } from "react"
import { useAppMessage } from "@/components/AppMessageProvider"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { useAuth } from "@/lib/auth"
import {
  createStylebookCatalog,
  deleteStylebookCatalog,
  getStylebookCatalogDeletePreview,
  listStylebookCatalogs,
  renameStylebookCatalog,
  setDefaultStylebookCatalog,
  type CatalogDeletePreview,
  type StylebookCatalogRow,
} from "@/lib/stylebook-org-api"

function sortCatalogs(rows: StylebookCatalogRow[]): StylebookCatalogRow[] {
  return [...rows].sort(
    (a, b) =>
      Number(b.is_default) - Number(a.is_default) ||
      a.name.localeCompare(b.name, undefined, { sensitivity: "base" }),
  )
}

export default function ManageCatalogsPage() {
  const { organizationId } = useAuth()
  const { showError, showMessage } = useAppMessage()

  const [rows, setRows] = useState<StylebookCatalogRow[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState("")

  const [createOpen, setCreateOpen] = useState(false)
  const [createName, setCreateName] = useState("")
  const [createDefault, setCreateDefault] = useState(false)
  const [creating, setCreating] = useState(false)

  const [renameRow, setRenameRow] = useState<StylebookCatalogRow | null>(null)
  const [renameValue, setRenameValue] = useState("")
  const [renaming, setRenaming] = useState(false)

  const [deleteRow, setDeleteRow] = useState<StylebookCatalogRow | null>(null)
  const [deletePreview, setDeletePreview] = useState<CatalogDeletePreview | null>(
    null,
  )
  const [deleteConfirmName, setDeleteConfirmName] = useState("")
  const [deleteReplacementId, setDeleteReplacementId] = useState<string>("")
  const [deleteLoading, setDeleteLoading] = useState(false)
  const [deleting, setDeleting] = useState(false)

  const sorted = useMemo(() => sortCatalogs(rows), [rows])

  const reload = useCallback(async () => {
    if (!organizationId) return
    setLoadError("")
    const list = await listStylebookCatalogs(organizationId)
    setRows(list)
  }, [organizationId])

  useEffect(() => {
    if (!organizationId) {
      setLoading(false)
      return
    }
    let cancelled = false
    setLoading(true)
    void (async () => {
      try {
        await reload()
      } catch (e) {
        if (!cancelled) {
          setLoadError(
            e instanceof Error ? e.message : "Could not load catalogs.",
          )
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [organizationId, reload])

  const notifyWorkspaceRefresh = () => {
    window.dispatchEvent(new CustomEvent("agate:workspaces-changed"))
  }

  const onCreate = async () => {
    if (!organizationId) return
    const name = createName.trim()
    if (!name) {
      showError("Please enter a name for the catalog.")
      return
    }
    try {
      setCreating(true)
      await createStylebookCatalog(organizationId, {
        name,
        is_default: createDefault,
      })
      setCreateOpen(false)
      setCreateName("")
      setCreateDefault(false)
      await reload()
      notifyWorkspaceRefresh()
      showMessage("Catalog created.", { title: "Done" })
    } catch (e) {
      showError(e instanceof Error ? e.message : "Could not create catalog.")
    } finally {
      setCreating(false)
    }
  }

  const onRename = async () => {
    if (!organizationId || !renameRow) return
    const name = renameValue.trim()
    if (!name) {
      showError("Please enter a name.")
      return
    }
    try {
      setRenaming(true)
      await renameStylebookCatalog(organizationId, renameRow.id, { name })
      setRenameRow(null)
      await reload()
      notifyWorkspaceRefresh()
      showMessage("Catalog updated.", { title: "Done" })
    } catch (e) {
      showError(e instanceof Error ? e.message : "Could not update name.")
    } finally {
      setRenaming(false)
    }
  }

  const onSetDefault = async (row: StylebookCatalogRow) => {
    if (!organizationId) return
    try {
      await setDefaultStylebookCatalog(organizationId, row.id)
      await reload()
      notifyWorkspaceRefresh()
      showMessage("Default catalog updated.", { title: "Done" })
    } catch (e) {
      showError(e instanceof Error ? e.message : "Could not update default.")
    }
  }

  const openDelete = async (row: StylebookCatalogRow) => {
    if (!organizationId) return
    setDeleteRow(row)
    setDeletePreview(null)
    setDeleteConfirmName("")
    setDeleteReplacementId("")
    setDeleteLoading(true)
    try {
      const p = await getStylebookCatalogDeletePreview(organizationId, row.id)
      setDeletePreview(p)
      if (p.is_only_stylebook_in_org) {
        setDeleteRow(null)
        setDeletePreview(null)
        showError(
          "Your organization must keep at least one catalog. Create another catalog before removing this one.",
        )
        return
      }
    } catch (e) {
      setDeleteRow(null)
      showError(e instanceof Error ? e.message : "Could not load delete details.")
    } finally {
      setDeleteLoading(false)
    }
  }

  const onDelete = async () => {
    if (!organizationId || !deleteRow || !deletePreview) return
    if (deleteConfirmName.trim() !== deleteRow.name.trim()) {
      showError("The name you typed does not match this catalog.")
      return
    }
    if (deleteRow.is_default) {
      const rep = parseInt(deleteReplacementId, 10)
      if (!Number.isFinite(rep) || rep === deleteRow.id) {
        showError("Choose which catalog should become the default.")
        return
      }
    }
    try {
      setDeleting(true)
      await deleteStylebookCatalog(organizationId, deleteRow.id, {
        confirm_name: deleteConfirmName.trim(),
        replacement_default_id: deleteRow.is_default
          ? parseInt(deleteReplacementId, 10)
          : null,
      })
      setDeleteRow(null)
      setDeletePreview(null)
      await reload()
      notifyWorkspaceRefresh()
      showMessage("Catalog removed.", { title: "Done" })
    } catch (e) {
      showError(e instanceof Error ? e.message : "Could not remove catalog.")
    } finally {
      setDeleting(false)
    }
  }

  const replacementChoices = useMemo(() => {
    if (!deleteRow) return []
    return sorted.filter((c) => c.id !== deleteRow.id)
  }, [deleteRow, sorted])

  if (!organizationId) {
    return (
      <div className="text-center text-muted-foreground py-12">
        You need to be signed in to an organization to manage catalogs.
      </div>
    )
  }

  if (loading) {
    return (
      <div className="text-center text-muted-foreground py-12">Loading…</div>
    )
  }

  if (loadError) {
    return (
      <div className="text-center text-destructive py-12">{loadError}</div>
    )
  }

  return (
    <div className="space-y-6 max-w-4xl">
      <div>
        <h1 className="text-3xl font-bold">Catalogs</h1>
        <p className="text-muted-foreground mt-2">
          Catalogs hold your canonical locations and related editorial data. Each
          workspace uses one catalog; flows can reference a catalog where
          supported.
        </p>
      </div>

      <div className="flex justify-end">
        <Button type="button" onClick={() => setCreateOpen(true)}>
          New catalog
        </Button>
      </div>

      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead className="w-40">Default</TableHead>
              <TableHead className="text-right w-64">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {sorted.map((r) => (
              <TableRow key={r.id}>
                <TableCell className="font-medium">{r.name}</TableCell>
                <TableCell>
                  {r.is_default ? (
                    <Badge variant="secondary">Default</Badge>
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )}
                </TableCell>
                <TableCell className="text-right space-x-2">
                  {!r.is_default ? (
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => void onSetDefault(r)}
                    >
                      Make default
                    </Button>
                  ) : null}
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setRenameRow(r)
                      setRenameValue(r.name)
                    }}
                  >
                    Rename
                  </Button>
                  <Button
                    type="button"
                    variant="destructive"
                    size="sm"
                    onClick={() => void openDelete(r)}
                  >
                    Remove
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>New catalog</DialogTitle>
            <DialogDescription>
              Add a catalog for your organization. You can switch workspaces to
              it later.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-2">
              <Label htmlFor="cat-name">Display name</Label>
              <Input
                id="cat-name"
                value={createName}
                onChange={(e) => setCreateName(e.target.value)}
                placeholder="e.g. Metro"
              />
            </div>
            <label className="flex items-center gap-2 text-sm">
              <Checkbox
                checked={createDefault}
                onCheckedChange={(v) => setCreateDefault(v === true)}
              />
              Make this the default catalog for the organization
            </label>
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setCreateOpen(false)}
            >
              Cancel
            </Button>
            <Button
              type="button"
              onClick={() => void onCreate()}
              disabled={creating}
            >
              {creating ? "Creating…" : "Create"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={renameRow != null}
        onOpenChange={(o) => !o && setRenameRow(null)}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Rename catalog</DialogTitle>
          </DialogHeader>
          <div className="space-y-2 py-2">
            <Label htmlFor="rename-cat">Display name</Label>
            <Input
              id="rename-cat"
              value={renameValue}
              onChange={(e) => setRenameValue(e.target.value)}
            />
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setRenameRow(null)}
            >
              Cancel
            </Button>
            <Button
              type="button"
              onClick={() => void onRename()}
              disabled={renaming}
            >
              {renaming ? "Saving…" : "Save"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={deleteRow != null && deletePreview != null}
        onOpenChange={(o) => {
          if (!o) {
            setDeleteRow(null)
            setDeletePreview(null)
          }
        }}
      >
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Remove catalog</DialogTitle>
            <DialogDescription>
              This cannot be undone. Type the catalog name exactly to confirm.
            </DialogDescription>
          </DialogHeader>
          {deleteLoading ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : deletePreview ? (
            <div className="space-y-4 text-sm">
              <p>
                <span className="font-medium">{deletePreview.name}</span>
                {deletePreview.graphs_referencing > 0 ||
                deletePreview.nodes_referencing > 0 ? (
                  <>
                    {" "}
                    is still referenced in{" "}
                    <span className="font-medium">
                      {deletePreview.graphs_referencing}
                    </span>{" "}
                    {deletePreview.graphs_referencing === 1 ? "flow" : "flows"}{" "}
                    and{" "}
                    <span className="font-medium">
                      {deletePreview.nodes_referencing}
                    </span>{" "}
                    {deletePreview.nodes_referencing === 1 ? "step" : "steps"}.
                    Remove or update those references first, or you may see errors
                    when running flows.
                  </>
                ) : (
                  <> has no flow references reported.</>
                )}
              </p>
              {deleteRow?.is_default && replacementChoices.length > 0 ? (
                <div className="space-y-2">
                  <Label>Default catalog after removal</Label>
                  <Select
                    value={deleteReplacementId}
                    onValueChange={setDeleteReplacementId}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Choose a catalog" />
                    </SelectTrigger>
                    <SelectContent>
                      {replacementChoices.map((c) => (
                        <SelectItem key={c.id} value={String(c.id)}>
                          {c.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              ) : null}
              <div className="space-y-2">
                <Label htmlFor="del-confirm">Type the catalog name to confirm</Label>
                <Input
                  id="del-confirm"
                  value={deleteConfirmName}
                  onChange={(e) => setDeleteConfirmName(e.target.value)}
                  autoComplete="off"
                />
              </div>
            </div>
          ) : null}
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                setDeleteRow(null)
                setDeletePreview(null)
              }}
            >
              Cancel
            </Button>
            <Button
              type="button"
              variant="destructive"
              onClick={() => void onDelete()}
              disabled={deleting || deleteLoading || !deletePreview}
            >
              {deleting ? "Removing…" : "Remove catalog"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
