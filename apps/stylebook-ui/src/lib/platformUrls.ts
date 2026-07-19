/** Cross-app navigation (Agate ↔ Stylebook SPAs). */

import { resolveUiOrigin } from "@backfield/ui/siblingUiOrigin"

function browserOrigin(): string {
  if (typeof window !== "undefined") {
    return window.location.origin
  }
  return ""
}

export function agateUiOrigin(): string {
  return resolveUiOrigin({
    envOverride: import.meta.env.VITE_AGATE_UI_ORIGIN,
    currentOrigin: browserOrigin(),
    targetApp: "agate",
  })
}

export function stylebookUiOrigin(): string {
  return resolveUiOrigin({
    envOverride: import.meta.env.VITE_STYLEBOOK_UI_ORIGIN,
    currentOrigin: browserOrigin(),
    targetApp: "stylebook",
  })
}

export function helpHref(): string {
  const raw = import.meta.env.VITE_HELP_URL
  if (typeof raw === "string" && raw.trim() !== "") {
    return raw.trim()
  }
  return `${agateUiOrigin()}/help`
}

function tenantSlug(currentOrigin: string): string {
  if (!currentOrigin) return ""
  const hostname = new URL(currentOrigin).hostname
  const labels = hostname.split(".")
  if (
    labels.length < 4 ||
    labels[labels.length - 2] !== "backfield" ||
    labels[labels.length - 1] !== "news" ||
    !["agate", "stylebook"].includes(labels[0] ?? "")
  ) {
    return ""
  }
  return labels[1]
}

/** Tenant-scoped API Playground with an explicit local-development target. */
export function playgroundHref(): string {
  const origin = browserOrigin()
  if (origin) {
    const url = new URL(origin)
    if (url.hostname === "localhost" || url.hostname === "127.0.0.1") {
      return `${url.protocol}//${url.hostname}:5176`
    }
  }
  const organizationSlug = tenantSlug(origin)
  const override = import.meta.env.VITE_PLAYGROUND_URL
  if (typeof override === "string" && override.trim() !== "") {
    return override.trim().replace("{organization_slug}", organizationSlug)
  }
  return organizationSlug
    ? `https://playground.${organizationSlug}.backfield.news`
    : "https://playground.backfield.news"
}

/** Agate SPA project home (flows, runs, settings). */
export function agateProjectHref(projectSlug: string): string {
  const base = agateUiOrigin().replace(/\/$/, "")
  return `${base}/project/${encodeURIComponent(projectSlug)}`
}

/** Agate SPA workspace hub. */
export function agateWorkspaceHref(workspaceSlug: string): string {
  const base = agateUiOrigin().replace(/\/$/, "")
  return `${base}/workspace/${encodeURIComponent(workspaceSlug)}`
}
