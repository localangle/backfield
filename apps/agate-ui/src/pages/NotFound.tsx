import { Link } from "react-router-dom"
import { Button } from "@/components/ui/button"

export default function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center gap-4 py-20 text-center">
      <p className="text-sm font-medium text-muted-foreground">404</p>
      <h1 className="text-3xl font-bold tracking-tight">Page not found</h1>
      <p className="max-w-md text-muted-foreground">
        This page doesn’t exist or may have moved. Check the address, or go back to Agate.
      </p>
      <Button asChild>
        <Link to="/">Back to Agate</Link>
      </Button>
    </div>
  )
}
