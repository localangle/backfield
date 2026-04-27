import type { ReactNode } from "react"
import { Navigate, Route, Routes } from "react-router-dom"
import { AppMessageProvider } from "@/components/AppMessageProvider"
import { AuthProvider, useAuth } from "@/lib/auth"
import Layout from "@/components/Layout"
import Index from "@/pages/Index"
import Login from "@/pages/Login"
import Locations from "@/pages/Locations"
import LocationDetail from "@/pages/LocationDetail"
import CreateLocation from "@/pages/CreateLocation"
import LocationCandidates from "@/pages/LocationCandidates"
import StubPage from "@/pages/StubPage"

function ProtectedRoute({ children }: { children: ReactNode }) {
  const { isAuthenticated, loading } = useAuth()

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-900 mx-auto" />
          <p className="mt-4 text-sm text-muted-foreground">Loading…</p>
        </div>
      </div>
    )
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }

  return <Layout>{children}</Layout>
}

export default function App() {
  return (
    <AuthProvider>
      <AppMessageProvider>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <Index />
            </ProtectedRoute>
          }
        />
        <Route
          path="/locations/candidates"
          element={
            <ProtectedRoute>
              <LocationCandidates />
            </ProtectedRoute>
          }
        />
        <Route
          path="/locations/canonical"
          element={
            <ProtectedRoute>
              <Locations />
            </ProtectedRoute>
          }
        />
        <Route
          path="/locations/canonical/:id"
          element={
            <ProtectedRoute>
              <LocationDetail />
            </ProtectedRoute>
          }
        />
        <Route
          path="/locations/create"
          element={
            <ProtectedRoute>
              <CreateLocation />
            </ProtectedRoute>
          }
        />
        <Route
          path="/import"
          element={
            <ProtectedRoute>
              <StubPage title="Import" />
            </ProtectedRoute>
          }
        />
        <Route
          path="/people/candidates"
          element={
            <ProtectedRoute>
              <StubPage title="People candidates" />
            </ProtectedRoute>
          }
        />
        <Route
          path="/organizations/candidates"
          element={
            <ProtectedRoute>
              <StubPage title="Organization candidates" />
            </ProtectedRoute>
          }
        />
        <Route
          path="/works/candidates"
          element={
            <ProtectedRoute>
              <StubPage title="Works candidates" />
            </ProtectedRoute>
          }
        />
        <Route
          path="/agents/:agentType"
          element={
            <ProtectedRoute>
              <StubPage title="Agents" />
            </ProtectedRoute>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      </AppMessageProvider>
    </AuthProvider>
  )
}
