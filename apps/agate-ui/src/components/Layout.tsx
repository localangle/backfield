import { ReactNode } from "react"
import { useNavigate } from "react-router-dom"
import { ShellProductBrand, UserAccountMenu } from "@backfield/ui"
import { useAuth } from "@/lib/auth"

interface LayoutProps {
  children: ReactNode
}

export default function Layout({ children }: LayoutProps) {
  const navigate = useNavigate()
  const { username, logout, isOrgAdmin } = useAuth()

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b shrink-0">
        <div className="px-4 py-4 flex justify-between items-center">
          <ShellProductBrand
            to="/"
            productTitle="Agate"
            platformSubtitle="Backfield Platform"
          />
          <div className="flex items-center gap-2">
            {username ? (
              <UserAccountMenu
                userLabel={username}
                isOrgAdmin={isOrgAdmin}
                onChangePassword={() => navigate("/account/password")}
                onManageUsers={
                  isOrgAdmin ? () => navigate("/admin/users") : undefined
                }
                onManageCatalogs={
                  isOrgAdmin ? () => navigate("/admin/stylebooks") : undefined
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
