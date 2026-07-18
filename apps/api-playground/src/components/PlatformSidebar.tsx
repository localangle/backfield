import { useEffect, useMemo, useState, type ReactNode } from "react"

import {
  LOCAL_AGATE_ORIGIN,
  LOCAL_STYLEBOOK_ORIGIN,
  deriveProductOrigin,
} from "../lib/origin"
import type { PlatformContext } from "../lib/session"
import PlaygroundMark from "./PlaygroundMark"

interface PlatformSidebarProps {
  context: PlatformContext
  organizationSlug: string
  local: boolean
}

function Icon({ children }: { children: ReactNode }) {
  return (
    <svg
      className="platform-nav-icon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {children}
    </svg>
  )
}

function AgateIcon() {
  return (
    <Icon>
      <rect width="7" height="9" x="3" y="3" rx="1" />
      <rect width="7" height="5" x="14" y="3" rx="1" />
      <rect width="7" height="9" x="14" y="12" rx="1" />
      <rect width="7" height="5" x="3" y="16" rx="1" />
    </Icon>
  )
}

function StylebookIcon() {
  return (
    <Icon>
      <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z" />
      <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z" />
    </Icon>
  )
}

function SettingsIcon() {
  return (
    <Icon>
      <path d="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z" />
      <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.83 2.83-.06-.06A1.7 1.7 0 0 0 15 19.4a1.7 1.7 0 0 0-1 .6 1.7 1.7 0 0 0-.4 1.1V21h-4v-.1A1.7 1.7 0 0 0 8 19.4a1.7 1.7 0 0 0-1.88.34l-.06.06-2.83-2.83.06-.06A1.7 1.7 0 0 0 3.6 15a1.7 1.7 0 0 0-.6-1 1.7 1.7 0 0 0-1.1-.4H2v-4h.1A1.7 1.7 0 0 0 3.6 8a1.7 1.7 0 0 0-.34-1.88l-.06-.06 2.83-2.83.06.06A1.7 1.7 0 0 0 8 3.6a1.7 1.7 0 0 0 1-.6 1.7 1.7 0 0 0 .4-1.1V2h4v.1A1.7 1.7 0 0 0 15 3.6a1.7 1.7 0 0 0 1.88-.34l.06-.06 2.83 2.83-.06.06A1.7 1.7 0 0 0 19.4 8a1.7 1.7 0 0 0 .6 1 1.7 1.7 0 0 0 1.1.4h.1v4h-.1A1.7 1.7 0 0 0 19.4 15Z" />
    </Icon>
  )
}

function HelpIcon() {
  return (
    <Icon>
      <circle cx="12" cy="12" r="10" />
      <path d="M9.1 9a3 3 0 1 1 5.8 1c0 2-3 2-3 4" />
      <path d="M12 18h.01" />
    </Icon>
  )
}

export default function PlatformSidebar({
  context,
  organizationSlug,
  local,
}: PlatformSidebarProps) {
  const [expanded, setExpanded] = useState(
    () =>
      typeof window.matchMedia !== "function" ||
      !window.matchMedia("(max-width: 700px)").matches,
  )
  const [expandedWorkspaces, setExpandedWorkspaces] = useState<Set<string>>(new Set())
  const agateOrigin = local
    ? LOCAL_AGATE_ORIGIN
    : deriveProductOrigin("agate", organizationSlug)
  const stylebookOrigin = local
    ? LOCAL_STYLEBOOK_ORIGIN
    : deriveProductOrigin("stylebook", organizationSlug)

  useEffect(() => {
    if (expandedWorkspaces.size || !context.workspaces[0]) {
      return
    }
    setExpandedWorkspaces(new Set([context.workspaces[0].slug]))
  }, [context.workspaces, expandedWorkspaces.size])

  const firstProjectSlug = useMemo(
    () => context.workspaces.flatMap((workspace) => workspace.projects)[0]?.slug,
    [context.workspaces],
  )

  function toggleWorkspace(slug: string) {
    setExpandedWorkspaces((current) => {
      const next = new Set(current)
      if (next.has(slug)) {
        next.delete(slug)
      } else {
        next.add(slug)
      }
      return next
    })
  }

  return (
    <aside
      className={`platform-sidebar ${expanded ? "platform-sidebar-expanded" : ""}`}
      aria-label="Platform"
    >
      <div className="platform-sidebar-header">
        {expanded && (
          <a
            href={agateOrigin}
            className="platform-organization"
            title={context.user.organizationName}
          >
            {context.user.organizationName}
          </a>
        )}
        <button
          type="button"
          className="platform-collapse"
          aria-expanded={expanded}
          aria-label={expanded ? "Collapse sidebar" : "Expand sidebar"}
          onClick={() => setExpanded((current) => !current)}
        >
          <span aria-hidden>{expanded ? "‹" : "›"}</span>
        </button>
      </div>

      <nav className="platform-navigation" aria-label="Backfield products">
        <div className="platform-navigation-scroll">
          <div className="platform-product-label">
            <AgateIcon />
            {expanded && <span>Agate</span>}
          </div>
          {expanded &&
            context.workspaces.map((workspace) => {
              const workspaceExpanded = expandedWorkspaces.has(workspace.slug)
              return (
                <div className="platform-workspace" key={workspace.id}>
                  <div className="platform-workspace-row">
                    <button
                      type="button"
                      className="platform-workspace-toggle"
                      aria-expanded={workspaceExpanded}
                      aria-label={`${workspaceExpanded ? "Collapse" : "Expand"} ${workspace.name}`}
                      onClick={() => toggleWorkspace(workspace.slug)}
                    >
                      <span aria-hidden>{workspaceExpanded ? "⌄" : "›"}</span>
                    </button>
                    <a
                      className="platform-workspace-link"
                      href={`${agateOrigin}/workspace/${encodeURIComponent(workspace.slug)}`}
                    >
                      {workspace.name}
                    </a>
                  </div>
                  {workspaceExpanded && (
                    <div className="platform-projects">
                      {workspace.projects.map((project) => (
                        <a
                          key={project.id}
                          href={`${agateOrigin}/project/${encodeURIComponent(project.slug)}`}
                        >
                          {project.name}
                        </a>
                      ))}
                    </div>
                  )}
                </div>
              )
            })}

          <div className="platform-section-rule" />
          <div className="platform-product-label">
            <StylebookIcon />
            {expanded && <span>Stylebook</span>}
          </div>
          {expanded &&
            context.stylebooks.map((stylebook) => {
              const params = new URLSearchParams()
              if (firstProjectSlug) params.set("project", firstProjectSlug)
              const query = params.toString()
              return (
                <a
                  className="platform-stylebook-link"
                  key={stylebook.id}
                  href={`${stylebookOrigin}/stylebook/${encodeURIComponent(stylebook.slug)}${
                    query ? `?${query}` : ""
                  }`}
                >
                  <span>{stylebook.name}</span>
                  {stylebook.is_default && <small>Default</small>}
                </a>
              )
            })}
        </div>

        <div className="platform-navigation-footer">
          {context.user.orgRole === "org_admin" && (
            <a href={`${agateOrigin}/settings`} title={expanded ? undefined : "Settings"}>
              <SettingsIcon />
              {expanded && <span>Settings</span>}
            </a>
          )}
          <a
            href={window.location.href}
            className="platform-link-active"
            aria-current="page"
            title={expanded ? undefined : "API Playground"}
          >
            <PlaygroundMark className="platform-nav-icon" />
            {expanded && <span>API Playground</span>}
          </a>
          <a href={`${agateOrigin}/help`} title={expanded ? undefined : "Help"}>
            <HelpIcon />
            {expanded && <span>Help</span>}
          </a>
        </div>
      </nav>
    </aside>
  )
}
