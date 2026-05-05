import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react"
import { ChevronLeft, ChevronRight } from "lucide-react"
import { cn } from "./cn"

export type ShellSidebarActions = { expand: () => void }

export type ShellSidebarChildren =
  | ReactNode
  | ((expanded: boolean, actions: ShellSidebarActions) => ReactNode)

export type ShellSidebarProps = {
  /** Browser storage key for persisting expanded vs collapsed (product-specific). */
  storageKey: string
  /** Used when nothing is stored yet (default: true). */
  defaultExpanded?: boolean
  /** Rendered in the top row only while expanded (same pattern as Agate’s workspace hub label). */
  headerLeading?: ReactNode
  /** Main navigation area; receive `expanded` via render prop when width-dependent layout matters. */
  children?: ShellSidebarChildren
  /** `aria-label` on the sidebar landmark (default: Main navigation). */
  asideAriaLabel?: string
}

function readBool(key: string, defaultVal: boolean): boolean {
  try {
    const v = localStorage.getItem(key)
    if (v === null) return defaultVal
    return v === "true"
  } catch {
    return defaultVal
  }
}

/**
 * Hub shell sidebar chrome aligned with Agate: fixed narrow / wide widths, border, muted strip,
 * header row with optional leading block and a collapse control.
 */
export function ShellSidebar({
  storageKey,
  defaultExpanded = true,
  headerLeading,
  children,
  asideAriaLabel = "Main navigation",
}: ShellSidebarProps) {
  const [expanded, setExpanded] = useState(() =>
    readBool(storageKey, defaultExpanded),
  )

  useEffect(() => {
    try {
      localStorage.setItem(storageKey, String(expanded))
    } catch {
      /* ignore */
    }
  }, [expanded, storageKey])

  const toggleSidebar = useCallback(() => setExpanded((e) => !e), [])
  const expand = useCallback(() => setExpanded(true), [])

  const actions: ShellSidebarActions = useMemo(() => ({ expand }), [expand])

  const body =
    typeof children === "function" ? children(expanded, actions) : children

  return (
    <aside
      className={cn(
        "flex flex-col border-r bg-muted/30 shrink-0 min-h-0 self-stretch transition-[width] duration-200 ease-out",
        expanded ? "w-56" : "w-14",
      )}
      aria-label={asideAriaLabel}
    >
      <div
        className={cn(
          "flex items-center min-w-0 p-2 border-b border-border/50",
          expanded ? "gap-1 justify-between" : "justify-center",
        )}
      >
        {expanded ? headerLeading : null}
        <button
          type="button"
          className={cn(
            "inline-flex items-center justify-center rounded-md text-sm font-medium ring-offset-background transition-colors",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
            "disabled:pointer-events-none disabled:opacity-50",
            "hover:bg-accent hover:text-accent-foreground",
            "h-8 w-8 shrink-0",
          )}
          onClick={toggleSidebar}
          aria-expanded={expanded}
          aria-label={expanded ? "Collapse sidebar" : "Expand sidebar"}
        >
          {expanded ? (
            <ChevronLeft className="h-4 w-4" aria-hidden />
          ) : (
            <ChevronRight className="h-4 w-4" aria-hidden />
          )}
        </button>
      </div>
      {body}
    </aside>
  )
}
