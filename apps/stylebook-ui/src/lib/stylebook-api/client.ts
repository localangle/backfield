export const stylebookApiBase = (): string =>
  import.meta.env.VITE_STYLEBOOK_API_BASE ?? "/api/stylebook"

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
      const errorJson = JSON.parse(errorText) as { detail?: string }
      errorMessage = errorJson.detail ?? errorMessage
    } catch {
      errorMessage = errorText || errorMessage
    }
    throw new Error(errorMessage)
  }
  return response.json() as Promise<T>
}
