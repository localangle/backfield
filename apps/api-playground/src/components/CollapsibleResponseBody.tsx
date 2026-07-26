type JsonGeometry = {
  type?: unknown
  coordinates?: unknown
}

type ResponseSegment =
  | { kind: "text"; text: string }
  | {
      kind: "geometry"
      text: string
      indentation: string
      propertyName: string
      geometryType: "Polygon" | "MultiPolygon"
      positionCount: number
      trailingComma: boolean
    }

function structuralBraceDelta(line: string): number {
  let delta = 0
  let inString = false
  let escaped = false
  for (const character of line) {
    if (escaped) {
      escaped = false
      continue
    }
    if (character === "\\" && inString) {
      escaped = true
      continue
    }
    if (character === '"') {
      inString = !inString
      continue
    }
    if (inString) continue
    if (character === "{") delta += 1
    if (character === "}") delta -= 1
  }
  return delta
}

function countPositions(value: unknown): number {
  if (!Array.isArray(value)) return 0
  if (
    value.length >= 2 &&
    typeof value[0] === "number" &&
    typeof value[1] === "number"
  ) {
    return 1
  }
  return value.reduce((total, child) => total + countPositions(child), 0)
}

function parseGeometryBlock(lines: string[], start: number): {
  end: number
  indentation: string
  propertyName: string
  geometryType: "Polygon" | "MultiPolygon"
  positionCount: number
  trailingComma: boolean
} | null {
  const opening = lines[start].match(/^(\s*)"([^"]*geometry[^"]*)":\s*\{\s*$/i)
  if (!opening) return null

  let depth = 0
  let end = start
  for (; end < lines.length; end += 1) {
    depth += structuralBraceDelta(lines[end])
    if (depth === 0) break
  }
  if (end >= lines.length || depth !== 0) return null

  const block = lines.slice(start, end + 1).join("\n")
  const colonIndex = block.indexOf(":")
  if (colonIndex < 0) return null
  const jsonText = block.slice(colonIndex + 1).trim().replace(/,\s*$/, "")

  try {
    const geometry = JSON.parse(jsonText) as JsonGeometry
    if (geometry.type !== "Polygon" && geometry.type !== "MultiPolygon") return null
    return {
      end,
      indentation: opening[1],
      propertyName: opening[2],
      geometryType: geometry.type,
      positionCount: countPositions(geometry.coordinates),
      trailingComma: lines[end].trimEnd().endsWith(","),
    }
  } catch {
    return null
  }
}

function segmentResponseBody(body: string): ResponseSegment[] | null {
  try {
    JSON.parse(body)
  } catch {
    return null
  }

  const lines = body.split("\n")
  const segments: ResponseSegment[] = []
  let textStart = 0

  for (let index = 0; index < lines.length; index += 1) {
    const geometry = parseGeometryBlock(lines, index)
    if (!geometry) continue

    if (index > textStart) {
      segments.push({ kind: "text", text: lines.slice(textStart, index).join("\n") })
    }
    segments.push({
      kind: "geometry",
      text: lines.slice(index, geometry.end + 1).join("\n"),
      indentation: geometry.indentation,
      propertyName: geometry.propertyName,
      geometryType: geometry.geometryType,
      positionCount: geometry.positionCount,
      trailingComma: geometry.trailingComma,
    })
    index = geometry.end
    textStart = geometry.end + 1
  }

  if (textStart < lines.length) {
    segments.push({ kind: "text", text: lines.slice(textStart).join("\n") })
  }
  return segments.some((segment) => segment.kind === "geometry") ? segments : null
}

export function CollapsibleResponseBody({ body }: { body: string }) {
  const displayBody = body || "Empty response body"
  const segments = segmentResponseBody(displayBody)
  if (!segments) return <pre>{displayBody}</pre>

  return (
    <div className="collapsible-response-body" aria-label="Response body">
      {segments.map((segment, index) => {
        const prefix = index > 0 ? "\n" : ""
        if (segment.kind === "text") {
          return <span key={`text-${index}`}>{prefix + segment.text}</span>
        }
        const countLabel = `${segment.positionCount.toLocaleString()} position${
          segment.positionCount === 1 ? "" : "s"
        }`
        return (
          <details className="response-geometry" key={`geometry-${index}`}>
            <summary
              aria-label={`Show ${segment.geometryType} geometry for ${segment.propertyName}`}
            >
              {`${prefix}${segment.indentation}"${segment.propertyName}": {…}${
                segment.trailingComma ? "," : ""
              } — ${segment.geometryType}, ${countLabel}`}
            </summary>
            <pre>{segment.text}</pre>
          </details>
        )
      })}
    </div>
  )
}
