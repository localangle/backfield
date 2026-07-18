import { useCallback, useEffect, useMemo, useState } from "react"
import {
  ChevronDown,
  ChevronRight,
  HelpCircle,
  Settings,
  TerminalSquare,
} from "lucide-react"
import { AgateProductMark } from "@backfield/ui/AgateProductMark"
import { StylebookProductMark } from "@backfield/ui/StylebookProductMark"
import { ShellSidebar } from "@backfield/ui/ShellSidebar"
import { cn } from "@backfield/ui/cn"

import {
  LOCAL_AGATE_ORIGIN,
  LOCAL_STYLEBOOK_ORIGIN,
  deriveProductOrigin,
} from "../lib/origin"
import type { PlatformContext } from "../lib/session"

const STORAGE_EXPANDED = "playground-sidebar-expanded"
const STORAGE_WORKSPACES_EXPANDED = "playground-sidebar-workspaces-expanded"

function readExpandedWorkspaceSlugs(): Set<string> {
  try {
    const raw = localStorage.getItem(STORAGE_WORKSPACES_EXPANDED)
    if (!raw) return new Set()
    const parsed = JSON.parse(raw) as unknown
    if (!Array.isArray(parsed)) return new Set()
    return new Set(parsed.filter((slug): slug is string => typeof slug === "string"))
  } catch {
    return new Set()
  }
}

interface PlatformSidebarProps {
  context: PlatformContext
  organizationSlug: string
  local: boolean
}

export default function PlatformSidebar({
  context,
  organizationSlug,
  local,
}: PlatformSidebarProps) {
  const [expandedWorkspaceSlugs, setExpandedWorkspaceSlugs] = useState<Set<string>>(
    readExpandedWorkspaceSlugs,
  )
  const agateOrigin = local
    ? LOCAL_AGATE_ORIGIN
    : deriveProductOrigin("agate", organizationSlug)
  const stylebookOrigin = local
    ? LOCAL_STYLEBOOK_ORIGIN
    : deriveProductOrigin("stylebook", organizationSlug)

  useEffect(() => {
    try {
      localStorage.setItem(
        STORAGE_WORKSPACES_EXPANDED,
        JSON.stringify([...expandedWorkspaceSlugs]),
      )
    } catch {
      /* ignore */
    }
  }, [expandedWorkspaceSlugs])

  const toggleWorkspaceExpanded = useCallback((workspaceSlug: string) => {
    setExpandedWorkspaceSlugs((prev) => {
      const next = new Set(prev)
      if (next.has(workspaceSlug)) next.delete(workspaceSlug)
      else next.add(workspaceSlug)
      return next
    })
  }, [])

  const firstProjectSlug = useMemo(
    () => context.workspaces.flatMap((workspace) => workspace.projects)[0]?.slug,
    [context.workspaces],
  )

  const sortedStylebooks = useMemo(() => {
    return [...context.stylebooks].sort(
      (a, b) =>
        Number(b.is_default) - Number(a.is_default) || a.name.localeCompare(b.name),
    )
  }, [context.stylebooks])

  const sectionTitleClass =
    "flex items-center gap-2 px-2 py-2 text-xs font-medium text-muted-foreground"

  const hubLinkClass = cn(
    "flex items-center gap-3 rounded-md px-2 py-2 text-sm font-medium transition-colors",
    "hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
    "text-muted-foreground hover:text-foreground",
  )

  // Matches Agate's AppSidebar workspace row (gap-1 px-2 py-2).
  const workspaceRowClass = cn(
    "rounded-md text-sm transition-colors",
    "flex w-full min-w-0 items-center gap-1 px-2 py-2 text-left font-medium",
    "text-foreground",
  )

  const projectUnderWorkspaceClass = cn(
    "rounded-md text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
    "flex w-full min-w-0 items-center py-1.5 pr-2 pl-7 text-left",
    "text-muted-foreground hover:bg-muted/50 hover:text-foreground",
  )

  return (
    <ShellSidebar
      storageKey={STORAGE_EXPANDED}
      asideAriaLabel="Platform"
      headerLeading={
        <a
          href={agateOrigin}
          title={context.user.organizationName}
          aria-label={context.user.organizationName}
          className={cn(
            "flex min-w-0 flex-1 items-center rounded-md px-1 py-1 -ml-1",
            "hover:bg-muted/35 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          )}
        >
          <span className="truncate text-sm font-semibold tracking-tight text-foreground">
            {context.user.organizationName}
          </span>
        </a>
      }
    >
      {(expanded: boolean, { expand }: { expand: () => void }) => (
        <nav
          className="flex flex-col flex-1 min-h-0 p-2 gap-0"
          aria-label="Backfield products"
        >
          <div className="flex-1 min-h-0 overflow-y-auto flex flex-col gap-2">
            {expanded ? (
              <div className={sectionTitleClass}>
                <AgateProductMark className="size-4 stroke-[1.75]" />
                <span>Agate</span>
              </div>
            ) : (
              <button
                type="button"
                title="Agate — workspaces"
                className={cn(
                  "inline-flex h-9 w-full items-center justify-center rounded-md",
                  "hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                )}
                onClick={() => expand()}
              >
                <AgateProductMark className="size-5 stroke-[1.75]" />
              </button>
            )}

            {(expanded ? context.workspaces : []).map((workspace) => {
              const workspaceExpanded = expandedWorkspaceSlugs.has(workspace.slug)
              const projectsSorted = [...workspace.projects].sort((a, b) =>
                a.name.localeCompare(b.name, undefined, { sensitivity: "base" }),
              )
              const projectsPanelId = `sidebar-workspace-projects-${workspace.slug}`
              return (
                <div
                  key={`${workspace.slug}-${workspace.id}`}
                  className="flex flex-col gap-0.5"
                >
                  <div className={cn(workspaceRowClass, "hover:bg-muted/60")}>
                    <button
                      type="button"
                      title={workspaceExpanded ? "Collapse" : "Expand"}
                      aria-label={`${workspaceExpanded ? "Collapse" : "Expand"} ${workspace.name}`}
                      aria-expanded={workspaceExpanded}
                      aria-controls={projectsPanelId}
                      onClick={() => toggleWorkspaceExpanded(workspace.slug)}
                      className={cn(
                        // Padding offset by negative margin keeps Agate's row
                        // geometry while giving the chevron a usable hit area.
                        "inline-flex shrink-0 items-center justify-center rounded-md p-1 -m-1",
                        "hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                      )}
                    >
                      {workspaceExpanded ? (
                        <ChevronDown
                          className="h-4 w-4 shrink-0 opacity-70"
                          aria-hidden
                        />
                      ) : (
                        <ChevronRight
                          className="h-4 w-4 shrink-0 opacity-70"
                          aria-hidden
                        />
                      )}
                    </button>
                    <a
                      href={`${agateOrigin}/workspace/${encodeURIComponent(workspace.slug)}`}
                      title={workspace.name}
                      aria-label={`Open workspace ${workspace.name} in Agate`}
                      className={cn(
                        "min-w-0 flex-1 truncate",
                        "hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-md",
                      )}
                    >
                      {workspace.name}
                    </a>
                  </div>
                  {workspaceExpanded ? (
                    <div id={projectsPanelId} className="flex flex-col gap-0.5">
                      {projectsSorted.map((project) => (
                        <a
                          key={`${workspace.slug}-p-${project.id}`}
                          href={`${agateOrigin}/project/${encodeURIComponent(project.slug)}`}
                          title={project.name}
                          aria-label={`Open project ${project.name} in Agate`}
                          className={projectUnderWorkspaceClass}
                        >
                          <span className="min-w-0 truncate">{project.name}</span>
                        </a>
                      ))}
                    </div>
                  ) : null}
                </div>
              )
            })}

            {context.workspaces.length === 0 && expanded ? (
              <div className="px-2 py-1.5 text-sm text-muted-foreground select-none">
                No workspaces available
              </div>
            ) : null}

            {sortedStylebooks.length > 0 ? (
              <>
                <div className="border-t border-border/50 my-1" />
                {expanded ? (
                  <div className={sectionTitleClass}>
                    <StylebookProductMark className="size-4 stroke-[1.75]" />
                    <span>Stylebook</span>
                  </div>
                ) : (
                  <button
                    type="button"
                    title="Stylebook"
                    className={cn(
                      "inline-flex h-9 w-full items-center justify-center rounded-md",
                      "hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                    )}
                    onClick={() => expand()}
                  >
                    <StylebookProductMark className="size-5 stroke-[1.75]" />
                  </button>
                )}
                {(expanded ? sortedStylebooks : []).map((stylebook) => {
                  const params = new URLSearchParams()
                  if (firstProjectSlug) params.set("project", firstProjectSlug)
                  const query = params.toString()
                  const openHref = `${stylebookOrigin}/stylebook/${encodeURIComponent(stylebook.slug)}${
                    query ? `?${query}` : ""
                  }`
                  return (
                    <a
                      key={stylebook.id}
                      href={openHref}
                      className={cn(
                        "rounded-md text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                        "flex w-full min-w-0 items-center justify-between gap-2 px-2 py-2 text-left",
                        "text-foreground hover:bg-muted/60",
                      )}
                      title={stylebook.name}
                      aria-label={`Open ${stylebook.name} in Stylebook`}
                    >
                      <span className="min-w-0 truncate">{stylebook.name}</span>
                      {stylebook.is_default ? (
                        <span className="shrink-0 rounded border border-border bg-background/80 px-1.5 py-0 text-[10px] font-medium text-muted-foreground">
                          Default
                        </span>
                      ) : null}
                    </a>
                  )
                })}
              </>
            ) : null}
          </div>

          <div className="border-t border-border/50 pt-2 shrink-0 space-y-1">
            {context.user.orgRole === "org_admin" ? (
              <a
                href={`${agateOrigin}/settings`}
                className={hubLinkClass}
                title={!expanded ? "Settings" : undefined}
              >
                <Settings className="h-5 w-5 shrink-0" aria-hidden />
                {expanded ? <span>Settings</span> : null}
              </a>
            ) : null}
            <a
              href={window.location.href}
              aria-current="page"
              className={cn(
                hubLinkClass,
                "bg-accent text-accent-foreground hover:text-accent-foreground",
              )}
              title={!expanded ? "API Playground" : undefined}
            >
              <TerminalSquare className="h-5 w-5 shrink-0" aria-hidden />
              {expanded ? <span>API Playground</span> : null}
            </a>
            <a
              href={`${agateOrigin}/help`}
              className={hubLinkClass}
              title={!expanded ? "Help" : undefined}
            >
              <HelpCircle className="h-5 w-5 shrink-0" aria-hidden />
              {expanded ? <span>Help</span> : null}
            </a>
          </div>
        </nav>
      )}
    </ShellSidebar>
  )
}
