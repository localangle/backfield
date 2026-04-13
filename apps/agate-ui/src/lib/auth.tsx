import { createContext, useContext, ReactNode } from 'react'

/**
 * Backfield has no auth-api in the default stack — treat the user as logged in
 * so the Agate UI routes work unchanged.
 */
interface AuthContextType {
  isAuthenticated: boolean
  username: string
  loading: boolean
  logout: () => Promise<void>
  checkAuth: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const value: AuthContextType = {
    isAuthenticated: true,
    username: 'dev',
    loading: false,
    async logout() {
      /* no-op */
    },
    async checkAuth() {
      /* no-op */
    },
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
