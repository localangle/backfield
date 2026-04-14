import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react"

import { fetchMe, type MeResponse } from "@/lib/core-api"

const authBase = () => import.meta.env.VITE_AUTH_API_BASE ?? ""

interface AuthContextType {
  isAuthenticated: boolean
  username: string
  userId: number | null
  organizationId: number | null
  orgRole: string | null
  isOrgAdmin: boolean
  loading: boolean
  logout: () => Promise<void>
  checkAuth: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

function applyMe(
  data: MeResponse,
  setters: {
    setIsAuthenticated: (v: boolean) => void
    setUsername: (v: string) => void
    setUserId: (v: number | null) => void
    setOrganizationId: (v: number | null) => void
    setOrgRole: (v: string | null) => void
    setIsOrgAdmin: (v: boolean) => void
  },
) {
  const ok = Boolean(data.authenticated && data.email)
  setters.setIsAuthenticated(ok)
  setters.setUsername(ok ? String(data.email) : "")
  setters.setUserId(ok && data.user_id != null ? data.user_id : null)
  setters.setOrganizationId(
    ok && data.organization_id != null ? data.organization_id : null,
  )
  const role = ok ? (data.org_role ?? null) : null
  setters.setOrgRole(role)
  setters.setIsOrgAdmin(ok && role === "org_admin")
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [username, setUsername] = useState("")
  const [userId, setUserId] = useState<number | null>(null)
  const [organizationId, setOrganizationId] = useState<number | null>(null)
  const [orgRole, setOrgRole] = useState<string | null>(null)
  const [isOrgAdmin, setIsOrgAdmin] = useState(false)
  const [loading, setLoading] = useState(true)

  const checkAuth = useCallback(async () => {
    try {
      const data = await fetchMe()
      applyMe(data, {
        setIsAuthenticated,
        setUsername,
        setUserId,
        setOrganizationId,
        setOrgRole,
        setIsOrgAdmin,
      })
    } catch {
      setIsAuthenticated(false)
      setUsername("")
      setUserId(null)
      setOrganizationId(null)
      setOrgRole(null)
      setIsOrgAdmin(false)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void checkAuth()
  }, [checkAuth])

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
    setOrgRole(null)
    setIsOrgAdmin(false)
  }, [])

  const value: AuthContextType = {
    isAuthenticated,
    username,
    userId,
    organizationId,
    orgRole,
    isOrgAdmin,
    loading,
    logout,
    checkAuth,
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
