import { Link, Outlet, useMatch } from 'react-router-dom'

/**
 * Organization Settings: hub at `/settings`, nested pages for models and integrations.
 */
export default function SettingsLayout() {
  const isHub = useMatch({ path: '/settings', end: true })

  return (
    <div className="w-full max-w-none min-w-0 space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        {isHub ? (
          <p className="text-sm text-muted-foreground">Manage organization settings.</p>
        ) : (
          <Link
            to="/settings"
            className="text-sm text-muted-foreground underline-offset-4 hover:text-foreground hover:underline inline-block"
          >
            All settings
          </Link>
        )}
      </div>

      <Outlet />
    </div>
  )
}
