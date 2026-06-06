import {
  parseLegacyStylebookQuery,
  parseStylebookSlugFromPath,
} from "@/lib/stylebookPaths"

export const stylebookApiBase = (): string =>
  import.meta.env.VITE_STYLEBOOK_API_BASE ?? "/api/stylebook"

/**
 * Legacy query key (`/?stylebook=`) kept only for redirects; canonical URLs use
 * ``/stylebook/<slug>/…``.
 */
export const STYLEBOOK_URL_QUERY_KEY = "stylebook"

function activeStylebookSlugFromBrowserUrl(): string | null {
  if (typeof window === "undefined") return null
  const fromPath = parseStylebookSlugFromPath(window.location.pathname)
  if (fromPath) return fromPath
  return parseLegacyStylebookQuery(window.location.search)
}

/**
 * Append catalog scope for Stylebook API calls from the current page URL
 * (`/stylebook/<slug>/…` or legacy ``?stylebook=<slug>``).
 */
export function augmentStylebookApiPath(path: string): string {
  const slug = activeStylebookSlugFromBrowserUrl()
  if (!slug) return path
  const cut = path.indexOf("?")
  const base = cut >= 0 ? path.slice(0, cut) : path
  const existing = cut >= 0 ? path.slice(cut + 1) : ""
  const params = new URLSearchParams(existing)
  if (!params.has("stylebook_slug")) {
    params.set("stylebook_slug", slug)
  }
  const q = params.toString()
  return q ? `${base}?${q}` : path
}

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

export class StylebookApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = "StylebookApiError"
    this.status = status
  }
}

export function isStylebookApiNotFoundError(error: unknown): boolean {
  return error instanceof StylebookApiError && error.status === 404
}

export async function stylebookJsonFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const resolvedPath = augmentStylebookApiPath(path)
  const response = await fetch(`${stylebookApiBase()}${resolvedPath}`, {
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
    throw new StylebookApiError(response.status, errorMessage)
  }
  return response.json() as Promise<T>
}
