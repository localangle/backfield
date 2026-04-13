import { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Button } from './ui/button'
import { useAuth } from '@/lib/auth'

interface LayoutProps {
  children: ReactNode
}

export default function Layout({ children }: LayoutProps) {
  const { username, logout } = useAuth()

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b">
        <div className="container mx-auto px-4 py-4 flex justify-between items-center">
          <div>
            <Link to="/" className="text-2xl font-bold">
              Backfield
            </Link>
            <p className="text-sm text-muted-foreground mt-1">
              Agate
            </p>
          </div>
          <div className="flex items-center gap-4">
            {username && (
              <span className="text-sm text-muted-foreground">
                {username}
              </span>
            )}
            <Button variant="outline" size="sm" onClick={logout}>
              Sign out
            </Button>
          </div>
        </div>
      </header>
      <main className="container mx-auto px-4 py-8">
        {children}
      </main>
    </div>
  )
}

