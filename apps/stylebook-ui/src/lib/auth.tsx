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
} from "@backfield/ui/tenantSession"

const authBase = () => import.meta.env.VITE_AUTH_API_BASE ?? ""

interface AuthContextType {
  isAuthenticated: boolean
  username: string
  organizationName: string | null
  organizationId: number | null
  organizationSlug: string | null
  organizations: OrganizationSwitcherOption[]
  /** `org_admin` in the current organization (same rule as Agate UI). */
  isOrgAdmin: boolean
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
    setOrganizationName: (v: string | null) => void
    setOrganizationId: (v: number | null) => void
    setOrganizationSlug: (v: string | null) => void
    setOrganizations: (v: OrganizationSwitcherOption[]) => void
    setIsOrgAdmin: (v: boolean) => void
  },
) {
  const ok = Boolean(data.authenticated && data.email)
  setters.setIsAuthenticated(ok)
  setters.setUsername(ok ? String(data.email) : "")
  setters.setOrganizationName(
    ok && data.organization_name != null && data.organization_name !== ""
      ? String(data.organization_name)
      : null,
  )
  setters.setOrganizationId(ok ? (data.organization_id ?? null) : null)
  setters.setOrganizationSlug(ok ? (data.organization_slug ?? null) : null)
  setters.setOrganizations(ok ? (data.organizations ?? []) : [])
  const role = ok ? (data.org_role ?? null) : null
  setters.setIsOrgAdmin(ok && role === "org_admin")
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [username, setUsername] = useState("")
  const [organizationName, setOrganizationName] = useState<string | null>(null)
  const [organizationId, setOrganizationId] = useState<number | null>(null)
  const [organizationSlug, setOrganizationSlug] = useState<string | null>(null)
  const [organizations, setOrganizations] = useState<OrganizationSwitcherOption[]>([])
  const [isOrgAdmin, setIsOrgAdmin] = useState(false)
  const [loading, setLoading] = useState(true)

  const checkAuth = useCallback(async () => {
    try {
      const data = await fetchMe()
      applyMe(data, {
        setIsAuthenticated,
        setUsername,
        setOrganizationName,
        setOrganizationId,
        setOrganizationSlug,
        setOrganizations,
        setIsOrgAdmin,
      })
    } catch {
      setIsAuthenticated(false)
      setUsername("")
      setOrganizationName(null)
      setOrganizationId(null)
      setOrganizationSlug(null)
      setOrganizations([])
      setIsOrgAdmin(false)
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
      setOrganizationName(null)
      setOrganizationId(null)
      setOrganizationSlug(null)
      setOrganizations([])
      setIsOrgAdmin(false)
    }
    window.addEventListener(
      ORGANIZATION_SELECTION_REQUIRED_EVENT,
      requireOrganizationSelection,
    )
    return () => {
      window.removeEventListener(
        ORGANIZATION_SELECTION_REQUIRED_EVENT,
        requireOrganizationSelection,
      )
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
    setOrganizationName(null)
    setOrganizationId(null)
    setOrganizationSlug(null)
    setOrganizations([])
    setIsOrgAdmin(false)
  }, [])

  const switchOrganization = useCallback(
    async (nextOrganizationId: number) => {
      const response = await handleTenantResponse(await fetch(`${authBase()}/v1/auth/switch-organization`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ organization_id: nextOrganizationId }),
      }))
      if (!response.ok) throw new Error("Could not switch organizations")
      const selected = organizations.find((item) => item.id === nextOrganizationId)
      clearTenantBrowserState()
      await checkAuth()
      return selected?.slug ?? ""
    },
    [checkAuth, organizations],
  )

  const value: AuthContextType = {
    isAuthenticated,
    username,
    organizationName,
    organizationId,
    organizationSlug,
    organizations,
    isOrgAdmin,
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
