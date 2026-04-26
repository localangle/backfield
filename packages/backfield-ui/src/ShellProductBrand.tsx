import { Link } from "react-router-dom"

import { cn } from "./cn"

export interface ShellProductBrandProps {
  /** Home (or root) route for the product shell. */
  to: string
  /** Primary product name — large title (e.g. Agate, Stylebook). */
  productTitle: string
  /** Platform line under the title (e.g. Backfield Platform). */
  platformSubtitle: string
  className?: string
}

/**
 * Hub-style brand block: large product title + muted “Backfield Platform” line.
 * Used by Agate UI and Stylebook UI for consistent top-bar labeling.
 */
export function ShellProductBrand({
  to,
  productTitle,
  platformSubtitle,
  className,
}: ShellProductBrandProps) {
  return (
    <Link
      to={to}
      className={cn("block hover:opacity-80 transition-opacity", className)}
    >
      <span className="block text-3xl font-bold tracking-tight">{productTitle}</span>
      <p className="mt-1 text-sm text-muted-foreground">{platformSubtitle}</p>
    </Link>
  )
}
