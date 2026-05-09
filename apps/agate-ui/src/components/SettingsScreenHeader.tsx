import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

/**
 * Shared heading for settings sub-pages: link back to Settings hub, then page title as main heading.
 */
export function SettingsScreenHeader({
  title,
  children,
}: {
  title: string
  children?: ReactNode
}) {
  return (
    <div className="space-y-1 min-w-0">
      <nav aria-label="Breadcrumb">
        <Link
          to="/settings"
          className="text-sm text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
        >
          Settings
        </Link>
      </nav>
      <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      {children != null ? <div className="text-sm text-muted-foreground pt-1">{children}</div> : null}
    </div>
  )
}
