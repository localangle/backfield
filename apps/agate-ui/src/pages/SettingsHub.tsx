import { NavLink } from 'react-router-dom'
import { BookOpen, Plug, Sparkles, Users } from 'lucide-react'

const settingsLinkClass =
  'flex w-full items-start gap-3 rounded-lg border border-border bg-background p-4 hover:bg-muted/40 transition-colors'

/**
 * Organization settings landing: links to AI models, Integrations, Users, and Stylebooks.
 */
export default function SettingsHub() {
  return (
    <div className="grid w-full gap-3">
      <NavLink to="/settings/models" className={settingsLinkClass}>
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

      <NavLink to="/settings/integrations" className={settingsLinkClass}>
        <Plug className="mt-0.5 h-5 w-5 shrink-0 text-muted-foreground" aria-hidden />
        <div className="min-w-0 flex-1">
          <div className="text-sm font-medium">Integrations</div>
          <div className="text-sm text-muted-foreground">
            Organization defaults for geocoding, search, and storage.
          </div>
        </div>
      </NavLink>

      <NavLink to="/admin/users" className={settingsLinkClass}>
        <Users className="mt-0.5 h-5 w-5 shrink-0 text-muted-foreground" aria-hidden />
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
          <div className="text-sm text-muted-foreground">Manage Stylebook catalogs.</div>
        </div>
      </NavLink>
    </div>
  )
}
