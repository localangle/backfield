import { useCallback, useEffect, useMemo, useState } from "react"
import { Loader2 } from "lucide-react"
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
import { SettingsScreenHeader } from "@/components/SettingsScreenHeader"
import { useAuth } from "@/lib/auth"
import {
  createBundleExportJob,
  createBundleImportJob,
  createStylebookCatalog,
  deleteStylebookCatalog,
  finalizeBundleImportJob,
  getBundleJob,
  getStylebookCatalogDeletePreview,
  listStylebookCatalogs,
  pollBundleJob,
  previewBundleManifest,
  renameStylebookCatalog,
  setDefaultStylebookCatalog,
  uploadBundleZipViaApi,
  type CatalogDeletePreview,
  type StylebookBundleManifestPreview,
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

  const [exportingId, setExportingId] = useState<number | null>(null)

  const [importOpen, setImportOpen] = useState(false)
  const [importFile, setImportFile] = useState<File | null>(null)
  const [importPreview, setImportPreview] =
    useState<StylebookBundleManifestPreview | null>(null)
  const [importPreviewLoading, setImportPreviewLoading] = useState(false)
  const [importName, setImportName] = useState("")
  const [importBusy, setImportBusy] = useState(false)

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
            e instanceof Error ? e.message : "Could not load stylebooks.",
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
      showError("Please enter a name for the stylebook.")
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
      showMessage("Stylebook created.", { title: "Done" })
    } catch (e) {
      showError(e instanceof Error ? e.message : "Could not create stylebook.")
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
      showMessage("Stylebook updated.", { title: "Done" })
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
      showMessage("Default stylebook updated.", { title: "Done" })
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
          "Your organization must keep at least one stylebook. Create another stylebook before removing this one.",
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
      showError("The name you typed does not match this stylebook.")
      return
    }
    if (deleteRow.is_default) {
      const rep = parseInt(deleteReplacementId, 10)
      if (!Number.isFinite(rep) || rep === deleteRow.id) {
        showError("Choose which stylebook should become the default.")
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
      showMessage("Stylebook removed.", { title: "Done" })
    } catch (e) {
      showError(e instanceof Error ? e.message : "Could not remove stylebook.")
    } finally {
      setDeleting(false)
    }
  }

  const replacementChoices = useMemo(() => {
    if (!deleteRow) return []
    return sorted.filter((c) => c.id !== deleteRow.id)
  }, [deleteRow, sorted])

  const openImport = () => {
    setImportOpen(true)
    setImportFile(null)
    setImportPreview(null)
    setImportName("")
  }

  const onImportFileChange = (file: File | null) => {
    setImportFile(file)
    setImportPreview(null)
    if (!file || !organizationId) {
      setImportPreviewLoading(false)
      return
    }
    setImportPreviewLoading(true)
    void (async () => {
      try {
        const prev = await previewBundleManifest(organizationId, file)
        setImportPreview(prev)
        const baseName = prev.source_stylebook?.name
          ? `${String(prev.source_stylebook.name)} copy`
          : "Imported stylebook"
        setImportName(baseName)
      } catch (e) {
        showError(e instanceof Error ? e.message : "Could not read that file.")
        setImportFile(null)
      } finally {
        setImportPreviewLoading(false)
      }
    })()
  }

  const onExportCatalog = async (row: StylebookCatalogRow) => {
    if (!organizationId) return
    const progressDlg = showMessage("Preparing a downloadable copy…", {
      title: "Export",
      pending: true,
    })
    try {
      setExportingId(row.id)
      const started = await createBundleExportJob(organizationId, row.id)
      const done = await pollBundleJob(organizationId, started.id)
      if (done.status === "failed") {
        progressDlg.dismiss()
        showError(done.error_message || "Export did not finish.")
        return
      }
      const withUrl = await getBundleJob(organizationId, started.id)
      const url = withUrl.download_url
      if (!url) {
        progressDlg.dismiss()
        showError("Download link is not available yet. Try again in a moment.")
        return
      }
      window.open(url, "_blank", "noopener,noreferrer")
      progressDlg.dismiss()
    } catch (e) {
      progressDlg.dismiss()
      showError(e instanceof Error ? e.message : "Export failed.")
    } finally {
      setExportingId(null)
    }
  }

  const onImportSubmit = async () => {
    if (!organizationId || !importFile || !importPreview) return
    const name = importName.trim()
    if (!name) {
      showError("Enter a name for the new stylebook.")
      return
    }
    setImportBusy(true)
    const progressDlg = showMessage("Preparing import…", {
      title: "Import",
      pending: true,
    })
    setImportOpen(false)
    try {
      const job = await createBundleImportJob(organizationId, {
        new_stylebook_name: name,
        project_mappings: {},
      })
      progressDlg.update("Uploading stylebook file…", { pending: true })
      await uploadBundleZipViaApi(organizationId, job.id, importFile)
      progressDlg.update("Finishing upload…", { pending: true })
      await finalizeBundleImportJob(organizationId, job.id)
      progressDlg.update("Import started. This may take a minute…", { pending: true })
      const done = await pollBundleJob(organizationId, job.id)
      progressDlg.dismiss()
      if (done.status === "failed") {
        showError(done.error_message || "Import did not finish.")
        return
      }
      await reload()
      notifyWorkspaceRefresh()
      showMessage("Stylebook imported.", { title: "Done" })
    } catch (e) {
      progressDlg.dismiss()
      showError(e instanceof Error ? e.message : "Import failed.")
    } finally {
      setImportBusy(false)
      setImportFile(null)
      setImportPreview(null)
      setImportName("")
    }
  }

  if (!organizationId) {
    return (
      <div className="text-center text-muted-foreground py-12">
        You need to be signed in to an organization to manage stylebooks.
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
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <SettingsScreenHeader title="Stylebooks">
          <>
            Stylebooks hold your organization&apos;s canonical locations, people, and related editorial data.{" "}
            Manage access to stylebooks via{" "}
            <span className="text-foreground font-medium">Users</span>.
          </>
        </SettingsScreenHeader>
        <div className="flex flex-row flex-nowrap items-center justify-end gap-2 shrink-0 self-start sm:self-auto">
          <Button type="button" className="shrink-0" onClick={() => setCreateOpen(true)}>
            New stylebook
          </Button>
          <Button type="button" variant="outline" className="shrink-0" onClick={openImport}>
            Import
          </Button>
        </div>
      </div>

      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead className="w-40">Default</TableHead>
              <TableHead className="text-right">Actions</TableHead>
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
                <TableCell className="text-right align-middle">
                  <div className="flex flex-nowrap items-center justify-end gap-2">
                    {!r.is_default ? (
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="shrink-0"
                        onClick={() => void onSetDefault(r)}
                      >
                        Make default
                      </Button>
                    ) : null}
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="shrink-0"
                      disabled={exportingId === r.id}
                      onClick={() => void onExportCatalog(r)}
                    >
                      {exportingId === r.id ? "Exporting…" : "Export"}
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="shrink-0"
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
                      className="shrink-0"
                      onClick={() => void openDelete(r)}
                    >
                      Remove
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <Dialog
        open={importOpen}
        onOpenChange={(o) => {
          if (importBusy) return
          setImportOpen(o)
        }}
      >
        <DialogContent
          className="sm:max-w-lg max-h-[90vh] overflow-y-auto"
          hideCloseButton={importBusy}
          onPointerDownOutside={(e) => {
            if (importBusy) e.preventDefault()
          }}
          onEscapeKeyDown={(e) => {
            if (importBusy) e.preventDefault()
          }}
        >
          <DialogHeader>
            <DialogTitle>Import a stylebook copy</DialogTitle>
            <DialogDescription>
              Upload a stylebook file you previously downloaded from this product. Canonical
              locations and people are copied; a new stylebook is created with new internal
              identifiers. Aliases, metadata, connections, and review queues are not included.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            {importBusy ? (
              <div
                className="flex items-center gap-2 text-sm text-muted-foreground"
                role="status"
                aria-live="polite"
                aria-busy
              >
                <Loader2 className="h-4 w-4 shrink-0 animate-spin" aria-hidden />
                Preparing import…
              </div>
            ) : null}
            <div className="space-y-2">
              <Label htmlFor="import-bundle">File</Label>
              <Input
                id="import-bundle"
                type="file"
                accept=".zip,application/zip"
                disabled={importBusy}
                onChange={(e) => {
                  const f = e.target.files?.[0] ?? null
                  onImportFileChange(f)
                }}
              />
              {importPreviewLoading ? (
                <p className="text-sm text-muted-foreground">Reading file…</p>
              ) : null}
            </div>
            {importPreview ? (
              <>
                <div className="space-y-2">
                  <Label htmlFor="import-name">Name for the new stylebook</Label>
                  <Input
                    id="import-name"
                    value={importName}
                    disabled={importBusy}
                    onChange={(e) => setImportName(e.target.value)}
                    placeholder="e.g. Metro (imported)"
                  />
                </div>
              </>
            ) : null}
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              disabled={importBusy}
              onClick={() => setImportOpen(false)}
            >
              Cancel
            </Button>
            <Button
              type="button"
              onClick={() => void onImportSubmit()}
              disabled={
                importBusy ||
                !importFile ||
                !importPreview ||
                importPreviewLoading ||
                !importName.trim()
              }
            >
              {importBusy ? "Importing…" : "Import"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>New stylebook</DialogTitle>
            <DialogDescription>
              Add a stylebook for your organization.
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
              Make this the default stylebook for the organization
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
            <DialogTitle>Rename stylebook</DialogTitle>
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
            <DialogTitle>Remove stylebook</DialogTitle>
            <DialogDescription>
              This cannot be undone. Type the stylebook name exactly to confirm.
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
                  <Label>Default stylebook after removal</Label>
                  <Select
                    value={deleteReplacementId}
                    onValueChange={setDeleteReplacementId}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Choose a stylebook" />
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
                <Label htmlFor="del-confirm">Type the stylebook name to confirm</Label>
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
              {deleting ? "Removing…" : "Remove stylebook"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
