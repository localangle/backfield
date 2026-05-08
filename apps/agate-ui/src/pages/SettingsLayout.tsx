import { Outlet, useMatch } from 'react-router-dom'

import { SettingsScreenHeader } from '@/components/SettingsScreenHeader'

const SECTION_TITLE: Record<string, string> = {
  models: 'AI models',
  integrations: 'Integrations',
}

/**
 * Organization Settings: hub at `/settings`, nested pages with breadcrumb + page title.
 */
export default function SettingsLayout() {
  const isHub = useMatch({ path: '/settings', end: true })
  const sectionMatch = useMatch('/settings/:section')
  const section = sectionMatch?.params.section
  const nestedTitle = section != null ? SECTION_TITLE[section] : undefined

  return (
    <div className="w-full max-w-none min-w-0 space-y-6">
      {isHub ? (
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
          <p className="text-sm text-muted-foreground">Manage organization settings.</p>
        </div>
      ) : nestedTitle != null ? (
        <SettingsScreenHeader title={nestedTitle} />
      ) : null}

      <Outlet />
    </div>
  )
}
