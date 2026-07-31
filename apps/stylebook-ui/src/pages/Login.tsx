import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { StylebookProductMark } from "@backfield/ui"
import { useAuth } from "@/lib/auth"

const AUTH_API_BASE = import.meta.env.VITE_AUTH_API_BASE ?? ""

interface OrganizationChoice {
  id: number
  name: string
  slug: string
}

interface LoginResponse {
  organization_selection_required?: boolean
  organizations?: OrganizationChoice[]
}

export default function Login() {
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)
  const [choosingOrganization, setChoosingOrganization] = useState(false)
  const [organizations, setOrganizations] = useState<OrganizationChoice[]>([])
  const navigate = useNavigate()
  const { checkAuth } = useAuth()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")
    setLoading(true)

    try {
      const response = await fetch(`${AUTH_API_BASE}/v1/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ email: email.trim().toLowerCase(), password }),
      })

      if (!response.ok) {
        const data = (await response.json()) as { detail?: string }
        setError(typeof data.detail === "string" ? data.detail : "Invalid email or password")
        return
      }

      const data = (await response.json()) as LoginResponse
      if (data.organization_selection_required) {
        setChoosingOrganization(true)
        setOrganizations(data.organizations ?? [])
        return
      }
      await checkAuth()
      navigate("/")
    } catch {
      setError("Failed to connect to server")
    } finally {
      setLoading(false)
    }
  }

  const selectOrganization = async (organization: OrganizationChoice) => {
    setLoading(true)
    setError("")
    try {
      const response = await fetch(`${AUTH_API_BASE}/v1/auth/select-organization`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          organization_id: organization.id,
        }),
      })
      if (!response.ok) {
        setError("Your organization selection expired. Please sign in again.")
        setChoosingOrganization(false)
        setOrganizations([])
        return
      }
      await checkAuth()
      navigate(`/org/${encodeURIComponent(organization.slug)}/`, { replace: true })
    } catch {
      setError("Could not select that organization. Please try again.")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex items-center justify-center min-h-screen bg-gray-50">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <StylebookProductMark className="size-7 stroke-[1.75]" />
            Stylebook
          </CardTitle>
          <CardDescription>Sign in with your Backfield account</CardDescription>
        </CardHeader>
        <CardContent>
          {choosingOrganization ? (
            <div className="space-y-3">
              <p className="text-sm text-muted-foreground">Choose an organization to continue.</p>
              {organizations.map((organization) => (
                <Button
                  key={organization.id}
                  type="button"
                  variant="outline"
                  className="w-full justify-start"
                  disabled={loading}
                  onClick={() => void selectOrganization(organization)}
                >
                  {organization.name}
                </Button>
              ))}
              {error ? <div role="alert" className="text-sm text-red-600">{error}</div> : null}
            </div>
          ) : <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoFocus
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>
            {error ? <div role="alert" className="text-sm text-red-600 bg-red-50 p-3 rounded">{error}</div> : null}
            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? "Signing in…" : "Sign in"}
            </Button>
          </form>}
        </CardContent>
      </Card>
    </div>
  )
}
