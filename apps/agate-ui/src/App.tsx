import type { ReactNode } from "react"
import { Routes, Route, Navigate, Outlet, useLocation, useNavigate } from "react-router-dom"
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
import WebhooksSettings from './pages/WebhooksSettings'
import OtherSettings from './pages/OtherSettings'
import SettingsLayout from './pages/SettingsLayout'
import SettingsHub from './pages/SettingsHub'
import HubLayout from './components/HubLayout'
import { AppMessageProvider } from '@/components/AppMessageProvider'
import { AuthProvider, useAuth } from './lib/auth'
import {
  ForcedPasswordChange,
  scopeOrganizationPath,
  shouldForcePasswordChange,
} from '@backfield/ui'
import { changePassword } from "@/lib/core-api"

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

function ProtectedHubLayout() {
  return (
    <ProtectedRoute>
      <HubLayout />
    </ProtectedRoute>
  )
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

function OrgAdminOutlet() {
  return (
    <OrgAdminRoute>
      <Outlet />
    </OrgAdminRoute>
  )
}

function AppRoutes() {
  const location = useLocation()
  const navigate = useNavigate()
  const {
    isAuthenticated,
    loading,
    organizationSlug,
    mustChangePassword,
    checkAuth,
    logout,
  } = useAuth()
  const pathScope = organizationSlug
    ? scopeOrganizationPath(location.pathname, location.search, organizationSlug)
    : null
  const scopedPathname = pathScope?.scopedPathname ?? location.pathname
  const shouldHealOrgPath =
    !loading &&
    isAuthenticated &&
    Boolean(organizationSlug) &&
    location.pathname !== "/login" &&
    Boolean(pathScope?.redirectPath)

  if (shouldForcePasswordChange({ loading, isAuthenticated, mustChangePassword })) {
    return (
      <ForcedPasswordChange
        changePassword={changePassword}
        onLogout={logout}
        onComplete={async () => {
          await checkAuth()
          navigate(
            organizationSlug
              ? `/org/${encodeURIComponent(organizationSlug)}/`
              : "/",
            { replace: true },
          )
        }}
      />
    )
  }

  return (
    <>
      {shouldHealOrgPath && pathScope?.redirectPath ? (
        <Navigate to={pathScope.redirectPath} replace />
      ) : null}
      <Routes location={{ ...location, pathname: scopedPathname }}>
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
          path="/flow/:graphId"
          element={
            <ProtectedRoute>
              <RunGraph />
            </ProtectedRoute>
          }
        />
        <Route element={<ProtectedHubLayout />}>
          <Route path="/" element={<WorkspacesHomePage />} />
          <Route path="/workspace/:workspaceSlug" element={<WorkspaceDetailPage />} />
          <Route path="/project/:projectSlug" element={<ProjectDetailPage />} />
          <Route path="/flows" element={<FlowsPage />} />
          <Route path="/runs" element={<RunsList />} />
          <Route path="/templates" element={<TemplatesPage />} />
          <Route path="/help" element={<HelpPlaceholderPage />} />
          <Route path="/account/password" element={<ChangePasswordPage />} />
          <Route path="/runs/:runId" element={<RunDetail />} />
          <Route path="/runs/:runId/items/:itemId" element={<ProcessedItemDetail />} />
          <Route path="/dev/leaflet-map" element={<LeafletMapHarness />} />
          <Route element={<OrgAdminOutlet />}>
            <Route path="/admin/users" element={<ManageUsers />} />
            <Route path="/admin/catalogs" element={<Navigate to="/admin/stylebooks" replace />} />
            <Route path="/admin/stylebooks" element={<ManageCatalogs />} />
            <Route path="/admin/ai-models" element={<Navigate to="/settings/models" replace />} />
            <Route path="/admin/integrations" element={<Navigate to="/settings/integrations" replace />} />
            <Route path="/settings" element={<SettingsLayout />}>
              <Route index element={<SettingsHub />} />
              <Route path="models" element={<AiModelsSettings />} />
              <Route path="integrations" element={<OrgIntegrationsSettings />} />
              <Route path="webhooks" element={<WebhooksSettings />} />
              <Route path="other" element={<OtherSettings />} />
              <Route path="*" element={<NotFound />} />
            </Route>
          </Route>
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </>
  )
}

function App() {
  return (
    <AuthProvider>
      <OrganizationApp />
    </AuthProvider>
  )
}

function OrganizationApp() {
  const { organizationId } = useAuth()
  return (
    <AppMessageProvider key={organizationId ?? "signed-out"}>
      <AppRoutes />
    </AppMessageProvider>
  )
}

export default App
