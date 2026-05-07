import { NavLink } from 'react-router-dom'

import { Card } from '@/components/ui/card'
import { useAuth } from '@/lib/auth'

export default function SettingsPage() {
  const { isOrgAdmin } = useAuth()

  return (
    <div className="max-w-3xl">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="text-sm text-muted-foreground">
          Manage organization settings.
        </p>
      </div>

      {!isOrgAdmin ? (
        <Card className="mt-6 p-4">
          <div className="text-sm text-muted-foreground">
            You don’t have access to settings.
          </div>
        </Card>
      ) : (
        <div className="mt-6 grid gap-3">
          <NavLink
            to="/admin/ai-models"
            className="block rounded-lg border border-border bg-background p-4 hover:bg-muted/40 transition-colors"
          >
            <div className="text-sm font-medium">AI models</div>
            <div className="text-sm text-muted-foreground">
              Configure model presets and credentials.
            </div>
          </NavLink>

          <NavLink
            to="/admin/users"
            className="block rounded-lg border border-border bg-background p-4 hover:bg-muted/40 transition-colors"
          >
            <div className="text-sm font-medium">Users</div>
            <div className="text-sm text-muted-foreground">
              Manage organization members and roles.
            </div>
          </NavLink>

          <NavLink
            to="/admin/stylebooks"
            className="block rounded-lg border border-border bg-background p-4 hover:bg-muted/40 transition-colors"
          >
            <div className="text-sm font-medium">Stylebooks</div>
            <div className="text-sm text-muted-foreground">
              Manage Stylebook catalogs.
            </div>
          </NavLink>
        </div>
      )}
    </div>
  )
}

