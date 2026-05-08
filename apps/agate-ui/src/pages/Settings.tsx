import { NavLink } from 'react-router-dom'
import { BookOpen, Sparkles, Users } from 'lucide-react'

import { Card } from '@/components/ui/card'
import { useAuth } from '@/lib/auth'

const settingsLinkClass =
  'flex w-full items-start gap-3 rounded-lg border border-border bg-background p-4 hover:bg-muted/40 transition-colors'

export default function SettingsPage() {
  const { isOrgAdmin } = useAuth()

  return (
    <div className="w-full">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="text-sm text-muted-foreground">
          Manage organization settings.
        </p>
      </div>

      {!isOrgAdmin ? (
        <Card className="mt-6 w-full p-4">
          <div className="text-sm text-muted-foreground">
            You don’t have access to settings.
          </div>
        </Card>
      ) : (
        <div className="mt-6 grid w-full gap-3">
          <NavLink to="/admin/ai-models" className={settingsLinkClass}>
            <Sparkles
              className="mt-0.5 h-5 w-5 shrink-0 text-muted-foreground"
              aria-hidden
            />
            <div className="min-w-0 flex-1">
              <div className="text-sm font-medium">AI models</div>
              <div className="text-sm text-muted-foreground">
                Configure model presets and credentials.
              </div>
            </div>
          </NavLink>

          <NavLink to="/admin/users" className={settingsLinkClass}>
            <Users
              className="mt-0.5 h-5 w-5 shrink-0 text-muted-foreground"
              aria-hidden
            />
            <div className="min-w-0 flex-1">
              <div className="text-sm font-medium">Users</div>
              <div className="text-sm text-muted-foreground">
                Manage organization members and roles.
              </div>
            </div>
          </NavLink>

          <NavLink to="/admin/stylebooks" className={settingsLinkClass}>
            <BookOpen
              className="mt-0.5 h-5 w-5 shrink-0 text-muted-foreground"
              aria-hidden
            />
            <div className="min-w-0 flex-1">
              <div className="text-sm font-medium">Stylebooks</div>
              <div className="text-sm text-muted-foreground">
                Manage Stylebook catalogs.
              </div>
            </div>
          </NavLink>
        </div>
      )}
    </div>
  )
}

