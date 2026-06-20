import { NavLink } from "react-router-dom"
import { useProjectCatalogScope } from "@/lib/catalogNavigation"
import { cn } from "@/lib/utils"

const tabClass = ({ isActive }: { isActive: boolean }) =>
  cn(
    "inline-flex items-center px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors",
    isActive
      ? "border-primary text-foreground"
      : "border-transparent text-muted-foreground hover:text-foreground hover:border-muted-foreground/40",
  )

export function StylebookHomeTabs() {
  const { catalogBasePath, catalogScopeSuffix } = useProjectCatalogScope()
  const cleanupPath = `${catalogBasePath}/cleanup${catalogScopeSuffix}`

  return (
    <nav className="flex gap-1 border-b border-border" aria-label="Stylebook home sections">
      <NavLink end to={`${catalogBasePath}${catalogScopeSuffix}`} className={tabClass}>
        Entities
      </NavLink>
      <NavLink to={cleanupPath} className={tabClass}>
        Checks
      </NavLink>
    </nav>
  )
}
