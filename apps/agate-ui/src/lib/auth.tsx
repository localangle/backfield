import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from 'react'

const authBase = () => import.meta.env.VITE_AUTH_API_BASE ?? ''

interface AuthContextType {
  isAuthenticated: boolean
  username: string
  loading: boolean
  logout: () => Promise<void>
  checkAuth: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [username, setUsername] = useState('')
  const [loading, setLoading] = useState(true)

  const checkAuth = useCallback(async () => {
    try {
      const response = await fetch(`${authBase()}/v1/auth/me`, {
        credentials: 'include',
      })
      if (!response.ok) {
        setIsAuthenticated(false)
        setUsername('')
        return
      }
      const data = (await response.json()) as {
        authenticated?: boolean
        email?: string
      }
      const ok = Boolean(data.authenticated && data.email)
      setIsAuthenticated(ok)
      setUsername(ok ? String(data.email) : '')
    } catch {
      setIsAuthenticated(false)
      setUsername('')
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
        method: 'POST',
        credentials: 'include',
      })
    } catch {
      /* still clear local session */
    }
    setIsAuthenticated(false)
    setUsername('')
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
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
