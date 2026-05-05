import { Link } from "react-router-dom"
import { ChevronRight } from "lucide-react"
import { cn } from "@/lib/utils"

export type BreadcrumbItem = { label: string; to?: string }

export function Breadcrumbs({
  items,
  className,
}: {
  items: BreadcrumbItem[]
  className?: string
}) {
  if (!items.length) return null

  return (
    <nav
      aria-label="Breadcrumb"
      className={cn(
        "flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-muted-foreground",
        className,
      )}
    >
      {items.map((item, idx) => {
        const isLast = idx === items.length - 1
        const content = (
          <span className={cn("min-w-0 truncate", isLast ? "text-foreground" : "")}>
            {item.label}
          </span>
        )

        return (
          <span key={`${idx}-${item.label}`} className="flex min-w-0 items-center gap-x-2">
            {idx > 0 ? (
              <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground/70" aria-hidden />
            ) : null}
            {item.to && !isLast ? (
              <Link
                to={item.to}
                className={cn(
                  "min-w-0 hover:text-foreground transition-colors",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm",
                )}
              >
                {content}
              </Link>
            ) : (
              content
            )}
          </span>
        )
      })}
    </nav>
  )
}

