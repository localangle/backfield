import { ReactNode } from "react"
import { Link, useNavigate } from "react-router-dom"
import { UserAccountMenu } from "@backfield/ui"
import { useAuth } from "@/lib/auth"

interface LayoutProps {
  children: ReactNode
}

export default function Layout({ children }: LayoutProps) {
  const navigate = useNavigate()
  const { username, logout, isOrgAdmin } = useAuth()

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b">
        <div className="container mx-auto px-4 py-4 flex justify-between items-center">
          <div>
            <Link to="/" className="text-2xl font-bold">
              Backfield
            </Link>
            <p className="text-sm text-muted-foreground mt-1">Agate</p>
          </div>
          <div className="flex items-center gap-2">
            {username ? (
              <UserAccountMenu
                userLabel={username}
                isOrgAdmin={isOrgAdmin}
                onChangePassword={() => navigate("/account/password")}
                onManageUsers={
                  isOrgAdmin ? () => navigate("/admin/users") : undefined
                }
                onLogout={() => void logout()}
              />
            ) : null}
          </div>
        </div>
      </header>
      <main className="container mx-auto px-4 py-8">{children}</main>
    </div>
  )
}
