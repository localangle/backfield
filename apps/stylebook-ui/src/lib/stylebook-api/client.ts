export const stylebookApiBase = (): string =>
  import.meta.env.VITE_STYLEBOOK_API_BASE ?? "/api/stylebook"

/** FastAPI may return `detail` as a string, object, or list of validation errors. */
function formatFastApiDetail(detail: unknown): string {
  if (detail == null) return ""
  if (typeof detail === "string") return detail
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === "string") return item
        if (item && typeof item === "object" && "msg" in item) {
          return String((item as { msg?: unknown }).msg ?? "")
        }
        try {
          return JSON.stringify(item)
        } catch {
          return String(item)
        }
      })
      .filter((s) => s.length > 0)
      .join("; ")
  }
  if (typeof detail === "object") {
    try {
      return JSON.stringify(detail)
    } catch {
      return String(detail)
    }
  }
  return String(detail)
}

export async function stylebookJsonFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${stylebookApiBase()}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
    credentials: "include",
  })
  if (!response.ok) {
    const errorText = await response.text()
    let errorMessage = `API error: ${response.statusText}`
    try {
      const errorJson = JSON.parse(errorText) as { detail?: unknown }
      if (errorJson.detail !== undefined) {
        const formatted = formatFastApiDetail(errorJson.detail)
        if (formatted) errorMessage = formatted
      }
    } catch {
      errorMessage = errorText || errorMessage
    }
    throw new Error(errorMessage)
  }
  return response.json() as Promise<T>
}
