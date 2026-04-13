import { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Button } from './ui/button'
import { useAuth } from '@/lib/auth'
import AppSidebar from './AppSidebar'

interface HubLayoutProps {
  children: ReactNode
}

export default function HubLayout({ children }: HubLayoutProps) {
  const { username, logout } = useAuth()

  return (
    <div className="h-dvh min-h-0 bg-background flex flex-col overflow-hidden">
      <header className="border-b shrink-0">
        <div className="px-4 py-4 flex justify-between items-center">
          <div>
            <Link to="/" className="text-3xl font-bold tracking-tight block">
              Agate
            </Link>
            <p className="text-sm text-muted-foreground mt-1">Backfield Platform</p>
          </div>
          <div className="flex items-center gap-4">
            {username && (
              <span className="text-sm text-muted-foreground">{username}</span>
            )}
            <Button variant="outline" size="sm" onClick={logout}>
              Sign out
            </Button>
          </div>
        </div>
      </header>
      <div className="flex flex-1 min-h-0">
        <AppSidebar />
        <main className="flex-1 min-w-0 overflow-auto">
          <div className="w-full max-w-none px-4 sm:px-6 lg:px-8 py-8">{children}</div>
        </main>
      </div>
    </div>
  )
}
