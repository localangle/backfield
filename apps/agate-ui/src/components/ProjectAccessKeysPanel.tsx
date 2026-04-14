import { useCallback, useEffect, useState } from "react"
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Key, Plus, Trash2, RefreshCw, AlertCircle, Copy } from "lucide-react"
import { format } from "date-fns"
import { useAuth } from "@/lib/auth"
import {
  createProjectAccessKey,
  listProjectAccessKeys,
  revokeProjectAccessKey,
  type ProjectAccessCredential,
  type ProjectAccessCredentialCreated,
} from "@/lib/core-api"

export default function ProjectAccessKeysPanel({
  projectId,
}: {
  projectId: number
}) {
  const { userId, isOrgAdmin } = useAuth()
  const [rows, setRows] = useState<ProjectAccessCredential[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const [createOpen, setCreateOpen] = useState(false)
  const [createType, setCreateType] = useState<"user" | "service">("user")
  const [createLabel, setCreateLabel] = useState("")

  const [rawKeyPayload, setRawKeyPayload] = useState<ProjectAccessCredentialCreated | null>(
    null,
  )
  const [rotateRevokeId, setRotateRevokeId] = useState<number | null>(null)

  const load = useCallback(async () => {
    setError(null)
    setLoading(true)
    try {
      const list = await listProjectAccessKeys(projectId)
      setRows(list)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load API access keys")
      setRows([])
    } finally {
      setLoading(false)
    }
  }, [projectId])

  useEffect(() => {
    void load()
  }, [load])

  const canRevoke = (row: ProjectAccessCredential): boolean => {
    if (row.credential_type === "service") {
      return isOrgAdmin
    }
    if (userId == null) return false
    return row.user_id === userId || isOrgAdmin
  }

  const canRotate = (row: ProjectAccessCredential): boolean => {
    if (row.credential_type === "service") {
      return isOrgAdmin
    }
    if (userId == null) return false
    return row.user_id === userId
  }

  const handleCreate = async () => {
    setSaving(true)
    setError(null)
    try {
      const created = await createProjectAccessKey(projectId, {
        credential_type: createType,
        label: createLabel.trim() || null,
      })
      setCreateOpen(false)
      setCreateLabel("")
      setCreateType("user")
      setRotateRevokeId(null)
      setRawKeyPayload(created)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create key")
    } finally {
      setSaving(false)
    }
  }

  const handleRevoke = async (row: ProjectAccessCredential) => {
    if (!canRevoke(row)) return
    if (
      !window.confirm(
        "Revoke this key? Clients using it will get 401 until they use a new key.",
      )
    ) {
      return
    }
    setSaving(true)
    setError(null)
    try {
      await revokeProjectAccessKey(projectId, row.id)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not revoke key")
    } finally {
      setSaving(false)
    }
  }

  const handleRotate = async (row: ProjectAccessCredential) => {
    if (!canRotate(row)) return
    if (
      !window.confirm(
        "Create a new key and revoke this one? Copy the new key before closing — the old key stops working after revoke.",
      )
    ) {
      return
    }
    setSaving(true)
    setError(null)
    try {
      const created = await createProjectAccessKey(projectId, {
        credential_type: row.credential_type as "user" | "service",
        label: row.label ? `Rotated (${row.label})` : `Rotated ${row.key_prefix.slice(0, 8)}…`,
      })
      setRotateRevokeId(row.id)
      setRawKeyPayload(created)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not rotate key")
    } finally {
      setSaving(false)
    }
  }

  const closeRawDialog = async (opts?: { revokeRotatedOld?: boolean }) => {
    const revokeOld =
      opts?.revokeRotatedOld === true &&
      rawKeyPayload &&
      rotateRevokeId != null
    if (revokeOld) {
      setSaving(true)
      setError(null)
      try {
        await revokeProjectAccessKey(projectId, rotateRevokeId)
        await load()
      } catch (e) {
        setError(
          e instanceof Error
            ? e.message
            : "New key was created but revoking the old key failed",
        )
      } finally {
        setSaving(false)
      }
    }
    setRawKeyPayload(null)
    setRotateRevokeId(null)
  }

  const copyRaw = (raw: string) => {
    void navigator.clipboard.writeText(raw)
  }

  return (
    <div className="w-full min-w-0 space-y-4 mb-10">
      <div>
        <h4 className="text-base font-semibold">API access keys</h4>
        <p className="text-sm text-muted-foreground mt-1">
          Use as <code className="text-xs bg-muted px-1 rounded">Authorization: Bearer &lt;key&gt;</code>{" "}
          when calling Backfield APIs for this project. The full secret is shown only once when
          created.
        </p>
      </div>

      {error ? (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => {
            setCreateOpen(true)
            setCreateType("user")
          }}
          disabled={saving}
        >
          <Plus className="h-4 w-4 mr-2" />
          New access key
        </Button>
      </div>

      {loading ? (
        <div className="text-sm text-muted-foreground py-4">Loading keys…</div>
      ) : rows.length === 0 ? (
        <Card>
          <CardContent className="text-center py-8">
            <Key className="h-10 w-10 mx-auto text-muted-foreground mb-3" />
            <p className="text-sm text-muted-foreground">
              No API access keys yet. Create one to authenticate scripts or integrations for this
              project.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {rows.map((row) => (
            <Card key={row.id}>
              <CardContent className="p-4">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <div className="flex-1 min-w-0 space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <code className="text-xs font-mono bg-muted px-2 py-0.5 rounded">
                        {row.key_prefix}…
                      </code>
                      <Badge variant="secondary" className="text-xs">
                        {row.credential_type}
                      </Badge>
                      {row.credential_type === "user" &&
                      userId != null &&
                      row.user_id === userId ? (
                        <Badge variant="outline" className="text-xs">
                          Yours
                        </Badge>
                      ) : null}
                    </div>
                    {row.label ? (
                      <p className="text-sm font-medium">{row.label}</p>
                    ) : null}
                    <p className="text-xs text-muted-foreground">
                      Created {format(new Date(row.created_at), "MMM d, yyyy HH:mm")}
                    </p>
                  </div>
                  <div className="flex gap-1 shrink-0">
                    {canRotate(row) ? (
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => void handleRotate(row)}
                        disabled={saving}
                        title="Create a replacement key and revoke this one"
                      >
                        <RefreshCw className="h-4 w-4" />
                      </Button>
                    ) : null}
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => void handleRevoke(row)}
                      disabled={saving || !canRevoke(row)}
                      className="text-destructive hover:text-destructive"
                      title={
                        !canRevoke(row)
                          ? "You cannot revoke this key"
                          : "Revoke key"
                      }
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create API access key</DialogTitle>
            <DialogDescription>
              {isOrgAdmin
                ? "Personal keys are tied to your account. Service keys are for automation (CI, bots) and can only be managed by organization admins."
                : "This key is tied to your account."}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            {isOrgAdmin ? (
              <div className="space-y-2">
                <Label>Key type</Label>
                <Select
                  value={createType}
                  onValueChange={(v) => setCreateType(v as "user" | "service")}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="user">Personal (user)</SelectItem>
                    <SelectItem value="service">Service (automation)</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            ) : null}
            <div className="space-y-2">
              <Label htmlFor="access-key-label">Label (optional)</Label>
              <Input
                id="access-key-label"
                value={createLabel}
                onChange={(e) => setCreateLabel(e.target.value)}
                placeholder="e.g. laptop, CI pipeline"
              />
            </div>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setCreateOpen(false)}>
              Cancel
            </Button>
            <Button type="button" onClick={() => void handleCreate()} disabled={saving}>
              {saving ? "Creating…" : "Create"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={!!rawKeyPayload}
        onOpenChange={(o) => {
          if (!o) {
            void closeRawDialog({ revokeRotatedOld: false })
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Copy your new key</DialogTitle>
            <DialogDescription>
              This is the only time the full secret is shown. Store it in a password manager or
              secret store.
            </DialogDescription>
          </DialogHeader>
          {rawKeyPayload ? (
            <div className="space-y-3">
              <div className="flex gap-2">
                <Input readOnly value={rawKeyPayload.raw_key} className="font-mono text-xs" />
                <Button
                  type="button"
                  variant="outline"
                  size="icon"
                  onClick={() => copyRaw(rawKeyPayload.raw_key)}
                  title="Copy"
                >
                  <Copy className="h-4 w-4" />
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">
                Header: <code className="bg-muted px-1 rounded">Authorization: Bearer &lt;key&gt;</code>
              </p>
            </div>
          ) : null}
          <DialogFooter>
            <Button
              type="button"
              onClick={() => {
                void closeRawDialog({
                  revokeRotatedOld: rotateRevokeId != null,
                })
              }}
            >
              {rotateRevokeId != null ? "Done (revoke old key)" : "Done"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
