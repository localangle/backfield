import { useCallback, useEffect, useState } from "react"
import { Building2, UserX } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
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
  createOrgUser,
  disableOrgUser,
  listOrgUsers,
  listOrgWorkspaces,
  patchOrgUser,
  replaceWorkspaceMemberships,
  type OrgUserRow,
  type WorkspaceWithProjects,
} from "@/lib/core-api"

export default function ManageUsersPage() {
  const { organizationId } = useAuth()
  const [users, setUsers] = useState<OrgUserRow[]>([])
  const [workspaces, setWorkspaces] = useState<WorkspaceWithProjects[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [createOpen, setCreateOpen] = useState(false)
  const [createEmail, setCreateEmail] = useState("")
  const [createPassword, setCreatePassword] = useState("")
  const [createDisplay, setCreateDisplay] = useState("")
  const [createRole, setCreateRole] = useState("member")
  const [accessUser, setAccessUser] = useState<OrgUserRow | null>(null)
  const [selectedWorkspaceIds, setSelectedWorkspaceIds] = useState<Set<number>>(
    new Set(),
  )

  const orgId = organizationId ?? 0

  const reload = useCallback(async () => {
    if (!organizationId) {
      return
    }
    setError("")
    const [u, w] = await Promise.all([
      listOrgUsers(organizationId, true),
      listOrgWorkspaces(organizationId),
    ])
    setUsers(u)
    setWorkspaces(w)
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
          setError(e instanceof Error ? e.message : "Failed to load users")
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [organizationId, reload])

  const openWorkspaceAccess = (u: OrgUserRow) => {
    setAccessUser(u)
    const selected = new Set<number>()
    for (const m of u.workspace_memberships ?? []) {
      selected.add(m.id)
    }
    setSelectedWorkspaceIds(selected)
  }

  const saveWorkspaceAccess = async () => {
    if (!accessUser || !organizationId) {
      return
    }
    await replaceWorkspaceMemberships(
      organizationId,
      accessUser.id,
      [...selectedWorkspaceIds],
    )
    setAccessUser(null)
    await reload()
  }

  const toggleWorkspace = (id: number) => {
    setSelectedWorkspaceIds((prev) => {
      const n = new Set(prev)
      if (n.has(id)) {
        n.delete(id)
      } else {
        n.add(id)
      }
      return n
    })
  }

  const handleCreate = async () => {
    if (!organizationId) {
      return
    }
    await createOrgUser(organizationId, {
      email: createEmail.trim().toLowerCase(),
      password: createPassword,
      display_name: createDisplay.trim() || null,
      role: createRole,
    })
    setCreateOpen(false)
    setCreateEmail("")
    setCreatePassword("")
    setCreateDisplay("")
    setCreateRole("member")
    await reload()
  }

  if (!organizationId) {
    return <p className="text-muted-foreground">No organization in session.</p>
  }

  if (loading) {
    return <div className="text-muted-foreground">Loading…</div>
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Users</h1>
          <p className="text-sm text-muted-foreground">
            Manage people and workspace access in your organization.
          </p>
        </div>
        <Button type="button" onClick={() => setCreateOpen(true)}>
          Add user
        </Button>
      </div>

      {error ? (
        <div className="text-sm text-destructive bg-destructive/10 p-3 rounded-md">{error}</div>
      ) : null}

      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Email</TableHead>
              <TableHead>Display name</TableHead>
              <TableHead>Org role</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {users.map((u) => (
              <TableRow key={u.id}>
                <TableCell className="font-medium">{u.email}</TableCell>
                <TableCell>{u.display_name ?? "—"}</TableCell>
                <TableCell>
                  <OrgRoleSelect
                    orgId={orgId}
                    user={u}
                    onUpdated={reload}
                  />
                </TableCell>
                <TableCell>
                  {u.disabled_at ? (
                    <span className="text-muted-foreground">Disabled</span>
                  ) : (
                    <span>Active</span>
                  )}
                </TableCell>
                <TableCell className="text-right align-middle">
                  <div className="flex flex-nowrap items-center justify-end gap-2">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="shrink-0 gap-1.5 max-lg:px-2.5"
                      disabled={!!u.disabled_at || u.role === "org_admin"}
                      onClick={() => openWorkspaceAccess(u)}
                      title={
                        u.role === "org_admin"
                          ? "Organization admins have access to all projects"
                          : "Manage workspace access"
                      }
                      aria-label="Manage workspace access"
                    >
                      <Building2 className="h-4 w-4 shrink-0" aria-hidden />
                      <span className="hidden lg:inline">Workspaces</span>
                    </Button>
                    <Button
                      type="button"
                      variant="destructive"
                      size="sm"
                      className="shrink-0 gap-1.5 max-lg:px-2.5"
                      disabled={!!u.disabled_at}
                      aria-label={`Disable ${u.email}`}
                      onClick={async () => {
                        if (
                          !window.confirm(
                            `Disable ${u.email}? They will not be able to sign in.`,
                          )
                        ) {
                          return
                        }
                        await disableOrgUser(orgId, u.id)
                        await reload()
                      }}
                    >
                      <UserX className="h-4 w-4 shrink-0" aria-hidden />
                      <span className="hidden lg:inline">Disable</span>
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add user</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-2">
              <Label htmlFor="c-email">Email</Label>
              <Input
                id="c-email"
                type="email"
                value={createEmail}
                onChange={(e) => setCreateEmail(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="c-pw">Temporary password</Label>
              <Input
                id="c-pw"
                type="password"
                value={createPassword}
                onChange={(e) => setCreatePassword(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="c-dn">Display name (optional)</Label>
              <Input
                id="c-dn"
                value={createDisplay}
                onChange={(e) => setCreateDisplay(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label>Organization role</Label>
              <Select value={createRole} onValueChange={setCreateRole}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="member">Member</SelectItem>
                  <SelectItem value="org_admin">Organization admin</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setCreateOpen(false)}>
              Cancel
            </Button>
            <Button
              type="button"
              onClick={() => void handleCreate().catch((e) => setError(String(e)))}
            >
              Create
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!accessUser} onOpenChange={(o) => !o && setAccessUser(null)}>
        <DialogContent className="max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Workspace access</DialogTitle>
            <p className="text-sm text-muted-foreground">
              {accessUser?.email} — members get all projects in each selected workspace.
            </p>
          </DialogHeader>
          <div className="space-y-4">
            {workspaces.length === 0 ? (
              <p className="text-sm text-muted-foreground">No workspaces in this organization.</p>
            ) : null}
            {workspaces.map((ws) => (
              <div key={ws.id} className="space-y-1 border-b border-border pb-3 last:border-0">
                <label className="flex items-center gap-2 text-sm font-medium cursor-pointer">
                  <input
                    type="checkbox"
                    className="rounded border-input"
                    checked={selectedWorkspaceIds.has(ws.id)}
                    onChange={() => toggleWorkspace(ws.id)}
                  />
                  <span>
                    {ws.name}{" "}
                    <span className="text-muted-foreground font-normal">({ws.slug})</span>
                  </span>
                </label>
                <p className="text-xs text-muted-foreground pl-6">
                  Projects:{" "}
                  {ws.projects.length
                    ? ws.projects.map((p) => p.name).join(", ")
                    : "None yet"}
                </p>
              </div>
            ))}
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setAccessUser(null)}>
              Cancel
            </Button>
            <Button
              type="button"
              onClick={() => void saveWorkspaceAccess().catch((e) => setError(String(e)))}
            >
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

function OrgRoleSelect({
  orgId,
  user,
  onUpdated,
}: {
  orgId: number
  user: OrgUserRow
  onUpdated: () => Promise<void>
}) {
  const [value, setValue] = useState(user.role)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    setValue(user.role)
  }, [user.id, user.role])

  return (
    <Select
      value={value}
      disabled={saving || !!user.disabled_at}
      onValueChange={(v) => {
        setValue(v)
        setSaving(true)
        void patchOrgUser(orgId, user.id, { role: v })
          .then(() => onUpdated())
          .catch((err) => {
            setValue(user.role)
            window.alert(err instanceof Error ? err.message : "Could not update role")
          })
          .finally(() => setSaving(false))
      }}
    >
      <SelectTrigger className="w-[180px]">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="member">Member</SelectItem>
        <SelectItem value="org_admin">Organization admin</SelectItem>
      </SelectContent>
    </Select>
  )
}
