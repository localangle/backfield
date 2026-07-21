import { Link } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { useProjectCatalogScope } from "@/lib/catalogNavigation"

export default function NotFound() {
  const { catalogBasePath, catalogScopeSuffix, stylebookSlug } = useProjectCatalogScope()
  const homeHref = stylebookSlug
    ? `${catalogBasePath}${catalogScopeSuffix}`
    : "/stylebook/default"

  return (
    <div className="flex flex-col items-center justify-center gap-4 py-20 text-center">
      <p className="text-sm font-medium text-muted-foreground">404</p>
      <h1 className="text-3xl font-bold tracking-tight">Page not found</h1>
      <p className="max-w-md text-muted-foreground">
        This page doesn’t exist or may have moved. Check the address, or go back to Stylebook.
      </p>
      <Button asChild>
        <Link to={homeHref}>Back to Stylebook</Link>
      </Button>
    </div>
  )
}
