import { ChevronRight } from 'lucide-react'
import { Link } from 'react-router-dom'

export type PageBreadcrumbItem = {
  label: string
  to?: string
}

export function PageBreadcrumbs({
  items,
  ariaLabel = 'Breadcrumb',
}: {
  items: PageBreadcrumbItem[]
  ariaLabel?: string
}) {
  return (
    <nav aria-label={ariaLabel}>
      <ol className="flex flex-wrap items-center gap-1.5 text-sm text-muted-foreground">
        {items.map((item, index) => (
          <li key={`${item.label}-${index}`} className="flex items-center gap-1.5 min-w-0">
            {item.to ? (
              <Link
                to={item.to}
                className="truncate underline-offset-4 hover:text-foreground hover:underline"
              >
                {item.label}
              </Link>
            ) : (
              <span className="truncate font-medium text-foreground">{item.label}</span>
            )}
            {index < items.length - 1 ? (
              <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground/70" aria-hidden />
            ) : null}
          </li>
        ))}
      </ol>
    </nav>
  )
}
