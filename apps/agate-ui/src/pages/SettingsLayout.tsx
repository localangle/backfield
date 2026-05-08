import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { cn } from '@/lib/utils'

const tabLinkClass = (active: boolean) =>
  cn(
    'inline-flex items-center rounded-md px-3 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
    active
      ? 'bg-accent text-accent-foreground'
      : 'text-muted-foreground hover:bg-muted/60 hover:text-foreground',
  )

const adminLinkClass =
  'text-sm text-muted-foreground underline-offset-4 hover:text-foreground hover:underline'

/**
 * Organization Settings shell: Models and Integrations (PRD integrations-settings).
 * Users and Stylebooks stay on existing /admin routes; linked here for discoverability.
 */
export default function SettingsLayout() {
  const location = useLocation()
  const onModels = location.pathname.endsWith('/models')
  const onIntegrations = location.pathname.endsWith('/integrations')

  return (
    <div className="w-full max-w-none min-w-0 space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
          <p className="text-sm text-muted-foreground">
            Organization defaults for AI models and external integrations.
          </p>
        </div>
        <nav className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm" aria-label="Other organization admin">
          <NavLink to="/admin/users" className={adminLinkClass}>
            Users
          </NavLink>
          <NavLink to="/admin/stylebooks" className={adminLinkClass}>
            Stylebooks
          </NavLink>
        </nav>
      </div>

      <div className="flex gap-1 border-b border-border pb-px">
        <NavLink
          to="/settings/models"
          className={() => tabLinkClass(onModels)}
          aria-current={onModels ? 'page' : undefined}
        >
          Models
        </NavLink>
        <NavLink
          to="/settings/integrations"
          className={() => tabLinkClass(onIntegrations)}
          aria-current={onIntegrations ? 'page' : undefined}
        >
          Integrations
        </NavLink>
      </div>

      <Outlet />
    </div>
  )
}
