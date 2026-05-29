import {
  Navigate,
  Outlet,
  Route,
  Routes,
  useLocation,
  useParams,
  useSearchParams,
} from "react-router-dom"
import { AppMessageProvider } from "@/components/AppMessageProvider"
import { AuthProvider, useAuth } from "@/lib/auth"
import {
  parseLegacyStylebookQuery,
  stripLegacyStylebookFromSearch,
} from "@/lib/stylebookPaths"
import Layout from "@/components/Layout"
import Index from "@/pages/Index"
import Login from "@/pages/Login"
import Locations from "@/pages/Locations"
import LocationDetail from "@/pages/LocationDetail"
import CreateLocation from "@/pages/CreateLocation"
import LocationCandidates from "@/pages/LocationCandidates"
import People from "@/pages/People"
import PersonCandidates from "@/pages/PersonCandidates"
import PersonDetail from "@/pages/PersonDetail"
import ImportLocations from "@/pages/ImportLocations"
import StubPage from "@/pages/StubPage"

function ProtectedLayout() {
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

  return (
    <Layout>
      <Outlet />
    </Layout>
  )
}

/** `/` — migrate legacy `?stylebook=` then default catalog. */
function RootEntryRedirect() {
  const { search } = useLocation()
  const slug = parseLegacyStylebookQuery(search) ?? "default"
  const qs = stripLegacyStylebookFromSearch(search)
  return (
    <Navigate to={`/stylebook/${encodeURIComponent(slug)}${qs}`} replace />
  )
}

function LegacyStylebookNavigate({ tail }: { tail: string }) {
  const { search } = useLocation()
  const slug = parseLegacyStylebookQuery(search) ?? "default"
  const qs = stripLegacyStylebookFromSearch(search)
  return (
    <Navigate to={`/stylebook/${encodeURIComponent(slug)}${tail}${qs}`} replace />
  )
}

function LegacyCanonicalDetailRedirect() {
  const { id } = useParams<{ id: string }>()
  const { search } = useLocation()
  const slug = parseLegacyStylebookQuery(search) ?? "default"
  const qs = stripLegacyStylebookFromSearch(search)
  const tail = `/locations/canonical/${encodeURIComponent(id ?? "")}`
  return (
    <Navigate to={`/stylebook/${encodeURIComponent(slug)}${tail}${qs}`} replace />
  )
}

function LegacyPersonCanonicalDetailRedirect() {
  const { id } = useParams<{ id: string }>()
  const { search } = useLocation()
  const slug = parseLegacyStylebookQuery(search) ?? "default"
  const qs = stripLegacyStylebookFromSearch(search)
  const tail = `/people/canonical/${encodeURIComponent(id ?? "")}`
  return (
    <Navigate to={`/stylebook/${encodeURIComponent(slug)}${tail}${qs}`} replace />
  )
}

function LegacyAgentRedirect() {
  const { agentType } = useParams<{ agentType: string }>()
  const { search } = useLocation()
  const slug = parseLegacyStylebookQuery(search) ?? "default"
  const qs = stripLegacyStylebookFromSearch(search)
  const tail = `/agents/${encodeURIComponent(agentType ?? "")}`
  return (
    <Navigate to={`/stylebook/${encodeURIComponent(slug)}${tail}${qs}`} replace />
  )
}

function LegacyImportRedirect() {
  const { search } = useLocation()
  const slug = parseLegacyStylebookQuery(search) ?? "default"
  const qs = stripLegacyStylebookFromSearch(search)
  return (
    <Navigate
      to={`/stylebook/${encodeURIComponent(slug)}/import/locations${qs}`}
      replace
    />
  )
}

function CatchAllRedirect() {
  const { search } = useLocation()
  const qs = stripLegacyStylebookFromSearch(search)
  return <Navigate to={`/stylebook/default${qs}`} replace />
}

export default function App() {
  return (
    <AuthProvider>
      <AppMessageProvider>
        <Routes>
          <Route path="/login" element={<Login />} />

          <Route element={<ProtectedLayout />}>
            <Route index element={<RootEntryRedirect />} />

            <Route
              path="/locations/candidates"
              element={<LegacyStylebookNavigate tail="/locations/candidates" />}
            />
            <Route
              path="/locations/canonical"
              element={<LegacyStylebookNavigate tail="/locations/canonical" />}
            />
            <Route
              path="/locations/canonical/:id"
              element={<LegacyCanonicalDetailRedirect />}
            />
            <Route
              path="/locations/create"
              element={<LegacyStylebookNavigate tail="/locations/create" />}
            />
            <Route path="/import" element={<LegacyImportRedirect />} />
            <Route
              path="/import/locations"
              element={<LegacyStylebookNavigate tail="/import/locations" />}
            />
            <Route
              path="/people/candidates"
              element={<LegacyStylebookNavigate tail="/people/candidates" />}
            />
            <Route
              path="/people/canonical"
              element={<LegacyStylebookNavigate tail="/people/canonical" />}
            />
            <Route
              path="/people/canonical/:id"
              element={<LegacyPersonCanonicalDetailRedirect />}
            />
            <Route
              path="/organizations/candidates"
              element={<LegacyStylebookNavigate tail="/organizations/candidates" />}
            />
            <Route
              path="/works/candidates"
              element={<LegacyStylebookNavigate tail="/works/candidates" />}
            />
            <Route path="/agents/:agentType" element={<LegacyAgentRedirect />} />

            <Route path="/stylebook/:stylebookSlug" element={<Outlet />}>
              <Route index element={<Index />} />
              <Route path="locations/candidates" element={<LocationCandidates />} />
              <Route path="locations/canonical" element={<Locations />} />
              <Route path="locations/canonical/:id" element={<LocationDetail />} />
              <Route path="locations/create" element={<CreateLocation />} />
              <Route path="import/locations" element={<ImportLocations />} />
              <Route path="people/candidates" element={<PersonCandidates />} />
              <Route path="people/canonical" element={<People />} />
              <Route path="people/canonical/:id" element={<PersonDetail />} />
              <Route
                path="organizations/candidates"
                element={<StubPage title="Organization candidates" />}
              />
              <Route
                path="works/candidates"
                element={<StubPage title="Works candidates" />}
              />
              <Route
                path="agents/:agentType"
                element={<StubPage title="Agents" />}
              />
            </Route>

            <Route path="*" element={<CatchAllRedirect />} />
          </Route>
        </Routes>
      </AppMessageProvider>
    </AuthProvider>
  )
}
