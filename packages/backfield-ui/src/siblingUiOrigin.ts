/** Split-host SPA origins for Backfield Cloud front doors. */

export type UiApp = "agate" | "stylebook"

/**
 * Map `agate.{client}…` ↔ `stylebook.{client}…` when the first DNS label is the
 * product host. Custom / same-origin hosts are left unchanged.
 */
export function swapUiHostname(hostname: string, target: UiApp): string {
  const labels = hostname.split(".")
  const first = labels[0]
  if (first === "agate" || first === "stylebook") {
    labels[0] = target
    return labels.join(".")
  }
  return hostname
}

/**
 * Resolve a cross-app origin.
 *
 * Prefer an explicit `VITE_*_UI_ORIGIN` override. Otherwise derive the sibling
 * host from the current browser origin so one shared UI artifact works for every
 * client (`agate.cpm.backfield.news` → `stylebook.cpm.backfield.news`, etc.).
 * Falls back to the current origin when the hostname is not a split UI host
 * (local same-origin / custom domains).
 */
export function resolveUiOrigin(opts: {
  envOverride?: string | null
  currentOrigin: string
  targetApp: UiApp
}): string {
  const override = typeof opts.envOverride === "string" ? opts.envOverride.trim() : ""
  if (override) {
    return override.replace(/\/$/, "")
  }

  const current = opts.currentOrigin.trim().replace(/\/$/, "")
  if (!current) {
    return ""
  }

  try {
    const url = new URL(current)
    url.hostname = swapUiHostname(url.hostname, opts.targetApp)
    return url.origin
  } catch {
    return current
  }
}
