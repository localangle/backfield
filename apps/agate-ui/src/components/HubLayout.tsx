import { ReactNode } from "react"
import { useNavigate } from "react-router-dom"
import { ShellProductBrand, UserAccountMenu } from "@backfield/ui"
import AppSidebar from "./AppSidebar"
import { useAuth } from "@/lib/auth"

interface HubLayoutProps {
  children: ReactNode
}

export default function HubLayout({ children }: HubLayoutProps) {
  const navigate = useNavigate()
  const { username, logout, isOrgAdmin } = useAuth()

  return (
    <div className="h-dvh min-h-0 bg-background flex flex-col overflow-hidden">
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
                onAiModelsSettings={
                  isOrgAdmin ? () => navigate("/admin/ai-models") : undefined
                }
                onLogout={() => void logout()}
              />
            ) : null}
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
