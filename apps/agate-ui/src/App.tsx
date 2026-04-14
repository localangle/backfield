import type { ReactNode } from "react"
import { Routes, Route, Navigate, useLocation } from "react-router-dom"
import HomeRedirect from './pages/HomeRedirect'
import ProjectDetailPage from './pages/ProjectDetailPage'
import FlowsPage from './pages/FlowsPage'
import RunsList from './pages/RunsList'
import TemplatesPage from './pages/TemplatesPage'
import SettingsPlaceholderPage from './pages/SettingsPlaceholderPage'
import HelpPlaceholderPage from './pages/HelpPlaceholderPage'
import RunGraph from './pages/RunGraph'
import GraphBuilder from './pages/GraphBuilder'
import RunDetail from './pages/RunDetail'
import ProcessedItemDetail from './pages/ProcessedItemDetail'
import Login from './pages/Login'
import ChangePasswordPage from './pages/ChangePassword'
import ManageUsers from './pages/ManageUsers'
import HubLayout from './components/HubLayout'
import { AuthProvider, useAuth } from './lib/auth'

function ProtectedRoute({ children }: { children: ReactNode }) {
  const { isAuthenticated, loading } = useAuth()
  const location = useLocation()

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-gray-600">Loading...</div>
      </div>
    )
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  return <>{children}</>
}

function OrgAdminRoute({ children }: { children: ReactNode }) {
  const { isOrgAdmin, loading, isAuthenticated } = useAuth()
  const location = useLocation()

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-muted-foreground">Loading...</div>
      </div>
    )
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  if (!isOrgAdmin) {
    return <Navigate to="/" replace />
  }

  return <>{children}</>
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        path="/flow/new"
        element={
          <ProtectedRoute>
            <GraphBuilder />
          </ProtectedRoute>
        }
      />
      <Route
        path="/flow/:graphId/edit"
        element={
          <ProtectedRoute>
            <GraphBuilder />
          </ProtectedRoute>
        }
      />
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <HomeRedirect />
          </ProtectedRoute>
        }
      />
      <Route
        path="/project/:projectSlug"
        element={
          <ProtectedRoute>
            <HubLayout>
              <ProjectDetailPage />
            </HubLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/flows"
        element={
          <ProtectedRoute>
            <HubLayout>
              <FlowsPage />
            </HubLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/runs"
        element={
          <ProtectedRoute>
            <HubLayout>
              <RunsList />
            </HubLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/templates"
        element={
          <ProtectedRoute>
            <HubLayout>
              <TemplatesPage />
            </HubLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/settings"
        element={
          <ProtectedRoute>
            <HubLayout>
              <SettingsPlaceholderPage />
            </HubLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/help"
        element={
          <ProtectedRoute>
            <HubLayout>
              <HelpPlaceholderPage />
            </HubLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/account/password"
        element={
          <ProtectedRoute>
            <HubLayout>
              <ChangePasswordPage />
            </HubLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/admin/users"
        element={
          <ProtectedRoute>
            <OrgAdminRoute>
              <HubLayout>
                <ManageUsers />
              </HubLayout>
            </OrgAdminRoute>
          </ProtectedRoute>
        }
      />
      <Route
        path="/flow/:graphId"
        element={
          <ProtectedRoute>
            <RunGraph />
          </ProtectedRoute>
        }
      />
      <Route
        path="/runs/:runId"
        element={
          <ProtectedRoute>
            <HubLayout>
              <RunDetail />
            </HubLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/runs/:runId/items/:itemId"
        element={
          <ProtectedRoute>
            <HubLayout>
              <ProcessedItemDetail />
            </HubLayout>
          </ProtectedRoute>
        }
      />
    </Routes>
  )
}

function App() {
  return (
    <AuthProvider>
      <AppRoutes />
    </AuthProvider>
  )
}

export default App
