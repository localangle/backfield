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

function withTenantContext(target: string, currentOrigin: string): string {
  if (!currentOrigin) return target
  const hostname = new URL(currentOrigin).hostname
  const labels = hostname.split(".")
  if (
    labels.length < 4 ||
    labels[labels.length - 2] !== "backfield" ||
    labels[labels.length - 1] !== "news" ||
    !["agate", "stylebook"].includes(labels[0] ?? "")
  ) {
    return target
  }
  const url = new URL(target)
  url.searchParams.set("organization", labels[1])
  return url.toString()
}

/** Standalone API Playground with tenant context and an explicit local-development target. */
export function playgroundHref(): string {
  const origin = browserOrigin()
  const override = import.meta.env.VITE_PLAYGROUND_URL
  if (typeof override === "string" && override.trim() !== "") {
    return withTenantContext(override.trim(), origin)
  }
  if (origin) {
    const url = new URL(origin)
    if (url.hostname === "localhost" || url.hostname === "127.0.0.1") {
      return `${url.protocol}//${url.hostname}:5176`
    }
  }
  return withTenantContext("https://playground.backfield.news", origin)
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
