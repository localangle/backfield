import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react"

import { fetchMe, type MeResponse } from "@/lib/core-api"
import type { OrganizationSwitcherOption } from "@backfield/ui"
import {
  clearTenantBrowserState,
  handleTenantResponse,
  ORGANIZATION_SELECTION_REQUIRED_EVENT,
  PASSWORD_CHANGE_REQUIRED_EVENT,
} from "@backfield/ui/tenantSession"

const authBase = () => import.meta.env.VITE_AUTH_API_BASE ?? ""

interface AuthContextType {
  isAuthenticated: boolean
  username: string
  userId: number | null
  organizationId: number | null
  organizationName: string | null
  organizationSlug: string | null
  organizations: OrganizationSwitcherOption[]
  orgRole: string | null
  isOrgAdmin: boolean
  mustChangePassword: boolean
  loading: boolean
  logout: () => Promise<void>
  checkAuth: () => Promise<void>
  switchOrganization: (organizationId: number) => Promise<string>
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

function applyMe(
  data: MeResponse,
  setters: {
    setIsAuthenticated: (v: boolean) => void
    setUsername: (v: string) => void
    setUserId: (v: number | null) => void
    setOrganizationId: (v: number | null) => void
    setOrganizationName: (v: string | null) => void
    setOrganizationSlug: (v: string | null) => void
    setOrganizations: (v: OrganizationSwitcherOption[]) => void
    setOrgRole: (v: string | null) => void
    setIsOrgAdmin: (v: boolean) => void
    setMustChangePassword: (v: boolean) => void
  },
) {
  const ok = Boolean(data.authenticated && data.email)
  setters.setIsAuthenticated(ok)
  setters.setUsername(ok ? String(data.email) : "")
  setters.setUserId(ok && data.user_id != null ? data.user_id : null)
  setters.setOrganizationId(
    ok && data.organization_id != null ? data.organization_id : null,
  )
  setters.setOrganizationName(
    ok && data.organization_name != null && data.organization_name !== ""
      ? String(data.organization_name)
      : null,
  )
  setters.setOrganizationSlug(ok ? (data.organization_slug ?? null) : null)
  setters.setOrganizations(ok ? (data.organizations ?? []) : [])
  const role = ok ? (data.org_role ?? null) : null
  setters.setOrgRole(role)
  setters.setIsOrgAdmin(ok && role === "org_admin")
  setters.setMustChangePassword(ok && Boolean(data.must_change_password))
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [username, setUsername] = useState("")
  const [userId, setUserId] = useState<number | null>(null)
  const [organizationId, setOrganizationId] = useState<number | null>(null)
  const [organizationName, setOrganizationName] = useState<string | null>(null)
  const [organizationSlug, setOrganizationSlug] = useState<string | null>(null)
  const [organizations, setOrganizations] = useState<OrganizationSwitcherOption[]>([])
  const [orgRole, setOrgRole] = useState<string | null>(null)
  const [isOrgAdmin, setIsOrgAdmin] = useState(false)
  const [mustChangePassword, setMustChangePassword] = useState(false)
  const [loading, setLoading] = useState(true)

  const checkAuth = useCallback(async () => {
    try {
      const data = await fetchMe()
      applyMe(data, {
        setIsAuthenticated,
        setUsername,
        setUserId,
        setOrganizationId,
        setOrganizationName,
        setOrganizationSlug,
        setOrganizations,
        setOrgRole,
        setIsOrgAdmin,
        setMustChangePassword,
      })
    } catch {
      setIsAuthenticated(false)
      setUsername("")
      setUserId(null)
      setOrganizationId(null)
      setOrganizationName(null)
      setOrganizationSlug(null)
      setOrganizations([])
      setOrgRole(null)
      setIsOrgAdmin(false)
      setMustChangePassword(false)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void checkAuth()
  }, [checkAuth])

  useEffect(() => {
    const requireOrganizationSelection = () => {
      clearTenantBrowserState()
      setIsAuthenticated(false)
      setUsername("")
      setUserId(null)
      setOrganizationId(null)
      setOrganizationName(null)
      setOrganizationSlug(null)
      setOrganizations([])
      setOrgRole(null)
      setIsOrgAdmin(false)
      setMustChangePassword(false)
    }
    window.addEventListener(
      ORGANIZATION_SELECTION_REQUIRED_EVENT,
      requireOrganizationSelection,
    )
    const requirePasswordChange = () => setMustChangePassword(true)
    window.addEventListener(PASSWORD_CHANGE_REQUIRED_EVENT, requirePasswordChange)
    return () => {
      window.removeEventListener(
        ORGANIZATION_SELECTION_REQUIRED_EVENT,
        requireOrganizationSelection,
      )
      window.removeEventListener(PASSWORD_CHANGE_REQUIRED_EVENT, requirePasswordChange)
    }
  }, [])

  const logout = useCallback(async () => {
    try {
      await fetch(`${authBase()}/v1/auth/logout`, {
        method: "POST",
        credentials: "include",
      })
    } catch {
      /* still clear local session */
    }
    setIsAuthenticated(false)
    setUsername("")
    setUserId(null)
    setOrganizationId(null)
    setOrganizationName(null)
    setOrganizationSlug(null)
    setOrganizations([])
    setOrgRole(null)
    setIsOrgAdmin(false)
    setMustChangePassword(false)
  }, [])

  const switchOrganization = useCallback(
    async (organizationId: number) => {
      const response = await handleTenantResponse(await fetch(`${authBase()}/v1/auth/switch-organization`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ organization_id: organizationId }),
      }))
      if (!response.ok) throw new Error("Could not switch organizations")
      const selected = organizations.find((item) => item.id === organizationId)
      clearTenantBrowserState()
      await checkAuth()
      return selected?.slug ?? ""
    },
    [checkAuth, organizations],
  )

  const value: AuthContextType = {
    isAuthenticated,
    username,
    userId,
    organizationId,
    organizationName,
    organizationSlug,
    organizations,
    orgRole,
    isOrgAdmin,
    mustChangePassword,
    loading,
    logout,
    checkAuth,
    switchOrganization,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider")
  }
  return context
}
