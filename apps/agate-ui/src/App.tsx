import type { ReactNode } from "react"
import { Routes, Route, Navigate, useLocation } from "react-router-dom"
import ProjectDetailPage from './pages/ProjectDetailPage'
import WorkspacesHomePage from './pages/WorkspacesHomePage'
import WorkspaceDetailPage from './pages/WorkspaceDetailPage'
import FlowsPage from './pages/FlowsPage'
import RunsList from './pages/RunsList'
import TemplatesPage from './pages/TemplatesPage'
import HelpPlaceholderPage from './pages/HelpPlaceholderPage'
import RunGraph from './pages/RunGraph'
import GuidedFlowBuilder from './pages/GuidedFlowBuilder'
import RunDetail from './pages/RunDetail'
import ProcessedItemDetail from './pages/ProcessedItemDetail'
import LeafletMapHarness from './pages/LeafletMapHarness'
import Login from './pages/Login'
import NotFound from './pages/NotFound'
import ChangePasswordPage from './pages/ChangePassword'
import ManageUsers from './pages/ManageUsers'
import ManageCatalogs from './pages/ManageCatalogs'
import AiModelsSettings from './pages/AiModelsSettings'
import OrgIntegrationsSettings from './pages/OrgIntegrationsSettings'
import SettingsLayout from './pages/SettingsLayout'
import SettingsHub from './pages/SettingsHub'
import HubLayout from './components/HubLayout'
import { AppMessageProvider } from '@/components/AppMessageProvider'
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
            <GuidedFlowBuilder />
          </ProtectedRoute>
        }
      />
      <Route
        path="/flow/:graphId/edit"
        element={
          <ProtectedRoute>
            <GuidedFlowBuilder />
          </ProtectedRoute>
        }
      />
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <HubLayout>
              <WorkspacesHomePage />
            </HubLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/workspace/:workspaceSlug"
        element={
          <ProtectedRoute>
            <HubLayout>
              <WorkspaceDetailPage />
            </HubLayout>
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
      <Route path="/admin/catalogs" element={<Navigate to="/admin/stylebooks" replace />} />
      <Route
        path="/admin/stylebooks"
        element={
          <ProtectedRoute>
            <OrgAdminRoute>
              <HubLayout>
                <ManageCatalogs />
              </HubLayout>
            </OrgAdminRoute>
          </ProtectedRoute>
        }
      />
      <Route path="/admin/ai-models" element={<Navigate to="/settings/models" replace />} />
      <Route path="/admin/integrations" element={<Navigate to="/settings/integrations" replace />} />
      <Route
        path="/settings"
        element={
          <ProtectedRoute>
            <OrgAdminRoute>
              <HubLayout>
                <SettingsLayout />
              </HubLayout>
            </OrgAdminRoute>
          </ProtectedRoute>
        }
      >
        <Route index element={<SettingsHub />} />
        <Route path="models" element={<AiModelsSettings />} />
        <Route path="integrations" element={<OrgIntegrationsSettings />} />
        <Route path="*" element={<NotFound />} />
      </Route>
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
      <Route
        path="/dev/leaflet-map"
        element={
          <ProtectedRoute>
            <HubLayout>
              <LeafletMapHarness />
            </HubLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="*"
        element={
          <ProtectedRoute>
            <HubLayout>
              <NotFound />
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
      <AppMessageProvider>
        <AppRoutes />
      </AppMessageProvider>
    </AuthProvider>
  )
}

export default App
