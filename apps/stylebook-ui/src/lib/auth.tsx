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
  },
) {
  const ok = Boolean(data.authenticated && data.email)
  setters.setIsAuthenticated(ok)
  setters.setUsername(ok ? String(data.email) : "")
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [username, setUsername] = useState("")
  const [loading, setLoading] = useState(true)

  const checkAuth = useCallback(async () => {
    try {
      const data = await fetchMe()
      applyMe(data, { setIsAuthenticated, setUsername })
    } catch {
      setIsAuthenticated(false)
      setUsername("")
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
  }, [])

  const value: AuthContextType = {
    isAuthenticated,
    username,
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
