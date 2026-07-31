export const ORGANIZATION_SELECTION_REQUIRED_EVENT =
  "backfield:organization-selection-required"

export function clearTenantBrowserState(): void {
  if (typeof window === "undefined") return
  for (const key of Object.keys(window.localStorage)) {
    if (/^(agate|stylebook|backfield)[-:]/.test(key)) {
      window.localStorage.removeItem(key)
    }
  }
  window.sessionStorage.clear()
}

export async function handleTenantResponse(response: Response): Promise<Response> {
  if (response.status !== 409 || typeof window === "undefined") return response
  try {
    const body = (await response.clone().json()) as {
      detail?: { code?: unknown }
    }
    if (body.detail?.code === "organization_selection_required") {
      clearTenantBrowserState()
      window.dispatchEvent(new Event(ORGANIZATION_SELECTION_REQUIRED_EVENT))
    }
  } catch {
    // Preserve the original response for its normal error handling.
  }
  return response
}
