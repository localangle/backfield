import { useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Upload } from "lucide-react"

interface SimpleGeoJsonGeometryProps {
  value: Record<string, unknown> | null
  onChange: (geometry: Record<string, unknown> | null) => void
}

export default function SimpleGeoJsonGeometry({ value, onChange }: SimpleGeoJsonGeometryProps) {
  const [text, setText] = useState("")
  const [error, setError] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const applyParsed = (obj: unknown) => {
    setError(null)
    if (!obj || typeof obj !== "object") {
      setError("Expected a JSON object.")
      return
    }
    const o = obj as Record<string, unknown>
    let geom: Record<string, unknown> | null = null
    if (o.type === "FeatureCollection" && Array.isArray(o.features) && o.features.length > 0) {
      const f = o.features[0] as Record<string, unknown>
      geom = (f.geometry as Record<string, unknown>) ?? null
    } else if (o.type === "Feature") {
      geom = (o.geometry as Record<string, unknown>) ?? null
    } else if (
      typeof o.type === "string" &&
      ["Point", "Polygon", "MultiPolygon", "LineString", "MultiLineString"].includes(String(o.type))
    ) {
      geom = o
    }
    if (!geom || typeof geom.type !== "string") {
      setError("No valid geometry found.")
      return
    }
    onChange(geom)
    setText(JSON.stringify(geom, null, 2))
  }

  const handleFile = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return
    try {
      const raw = await file.text()
      applyParsed(JSON.parse(raw))
    } catch {
      setError("Invalid JSON file.")
    }
    event.target.value = ""
  }

  const handlePasteApply = () => {
    try {
      applyParsed(JSON.parse(text))
    } catch {
      setError("Invalid JSON.")
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <Label>Paste GeoJSON geometry or Feature / FeatureCollection</Label>
        <Textarea
          className="mt-2 font-mono text-xs min-h-[140px]"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder='{"type":"Point","coordinates":[-87.6,41.8]}'
        />
        <Button type="button" variant="secondary" className="mt-2" onClick={handlePasteApply}>
          Apply from text
        </Button>
      </div>
      <div>
        <input
          ref={fileRef}
          type="file"
          accept=".geojson,.json"
          onChange={handleFile}
          className="hidden"
        />
        <Button type="button" variant="outline" onClick={() => fileRef.current?.click()}>
          <Upload className="h-4 w-4 mr-2" />
          Choose GeoJSON file
        </Button>
      </div>
      {error && <p className="text-sm text-destructive">{error}</p>}
      {value && (
        <p className="text-sm text-muted-foreground">
          Current geometry type: <span className="font-medium">{String(value.type)}</span>
        </p>
      )}
    </div>
  )
}
