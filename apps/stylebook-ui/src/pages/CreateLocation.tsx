import { useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"
import { createLocation } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import SimpleGeoJsonGeometry from "@/components/SimpleGeoJsonGeometry"
import { Loader2 } from "lucide-react"

export default function CreateLocation() {
  const navigate = useNavigate()
  const [projectSlug, setProjectSlug] = useState("")
  const [name, setName] = useState("")
  const [locationType, setLocationType] = useState("")
  const [formattedAddress, setFormattedAddress] = useState("")
  const [geometry, setGeometry] = useState<Record<string, unknown> | null>(null)
  const [creating, setCreating] = useState(false)

  useEffect(() => {
    const slug = new URLSearchParams(window.location.search).get("project") || ""
    setProjectSlug(slug)
  }, [])

  const handleSubmit = async () => {
    if (!name.trim()) {
      alert("Please enter a location name")
      return
    }
    if (!locationType.trim()) {
      alert("Please enter a location type")
      return
    }

    try {
      setCreating(true)
      const location = await createLocation(projectSlug, {
        name: name.trim(),
        location_type: locationType.trim(),
        formatted_address: formattedAddress.trim() || undefined,
        geometry_json: geometry ?? undefined,
        status: "active",
      })
      navigate(`/locations/canonical/${location.id}?project=${projectSlug}`)
    } catch (error) {
      console.error("Failed to create location:", error)
      alert(`Failed to create location: ${error instanceof Error ? error.message : "Unknown error"}`)
    } finally {
      setCreating(false)
    }
  }

  const handleCancel = () => {
    navigate(`/locations/canonical?project=${projectSlug}`)
  }

  return (
    <div className="container mx-auto p-6">
      <div className="mb-6">
        <h1 className="text-3xl font-bold">Create Location</h1>
      </div>

      <div className="grid grid-cols-12 gap-6">
        <div className="col-span-6">
          <Card>
            <CardHeader>
              <CardTitle>Location Details</CardTitle>
              <CardDescription>Enter the basic information for this location</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <Label htmlFor="name">Name *</Label>
                <Input
                  id="name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g., Chicago, IL"
                />
              </div>
              <div>
                <Label htmlFor="locationType">Location Type *</Label>
                <Input
                  id="locationType"
                  value={locationType}
                  onChange={(e) => setLocationType(e.target.value)}
                  placeholder="e.g., city, neighborhood, ward"
                />
              </div>
              <div>
                <Label htmlFor="formattedAddress">Formatted Address</Label>
                <Input
                  id="formattedAddress"
                  value={formattedAddress}
                  onChange={(e) => setFormattedAddress(e.target.value)}
                  placeholder="e.g., Chicago, IL, United States"
                />
              </div>
            </CardContent>
          </Card>
        </div>

        <div className="col-span-6">
          <Card>
            <CardHeader>
              <CardTitle>Geometry</CardTitle>
              <CardDescription>Optional GeoJSON geometry (Point, Polygon, etc.)</CardDescription>
            </CardHeader>
            <CardContent>
              <SimpleGeoJsonGeometry value={geometry} onChange={setGeometry} />
            </CardContent>
          </Card>
        </div>
      </div>

      <div className="mt-6 flex justify-end gap-2">
        <Button variant="outline" onClick={handleCancel} disabled={creating}>
          Cancel
        </Button>
        <Button onClick={handleSubmit} disabled={creating || !name.trim() || !locationType.trim()}>
          {creating ? (
            <>
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              Creating...
            </>
          ) : (
            "Create Location"
          )}
        </Button>
      </div>
    </div>
  )
}
