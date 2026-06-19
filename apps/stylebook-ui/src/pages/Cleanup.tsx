import { useEffect, useMemo, useState } from "react"
import { Link } from "react-router-dom"
import { Breadcrumbs } from "@/components/Breadcrumbs"
import { StylebookHomeTabs } from "@/components/StylebookHomeTabs"
import { useAppMessage } from "@/components/AppMessageProvider"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Loader2 } from "lucide-react"
import { useProjectCatalogScope } from "@/lib/catalogNavigation"
import { useScopeBreadcrumbRoot } from "@/lib/breadcrumbs"
import { useSelectedStylebookLabel } from "@/lib/stylebookScopeContext"
import { CLEANUP_CHECK_CONFIGS } from "@/lib/cleanupChecks"
import { listCleanupChecks, type CleanupCheck } from "@/lib/api"

export default function Cleanup() {
  const { showError } = useAppMessage()
  const { stylebookSlug, catalogBasePath, catalogScopeSuffix, projectFilterSlug } =
    useProjectCatalogScope()
  const crumbRoot = useScopeBreadcrumbRoot()
  const selectedStylebookLabel = useSelectedStylebookLabel()
  const [loading, setLoading] = useState(true)
  const [checks, setChecks] = useState<CleanupCheck[]>([])

  useEffect(() => {
    let cancelled = false
    async function load() {
      if (!stylebookSlug) return
      setLoading(true)
      try {
        const response = await listCleanupChecks({
          stylebookSlug,
          project: projectFilterSlug || undefined,
        })
        if (!cancelled) setChecks(response.checks)
      } catch (error) {
        if (!cancelled) {
          showError(error instanceof Error ? error.message : "Failed to load cleanup checks")
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [stylebookSlug, projectFilterSlug, showError])

  const checksById = useMemo(() => new Map(checks.map((check) => [check.id, check])), [checks])

  return (
    <div className="space-y-6">
      <div>
        <Breadcrumbs items={[{ label: crumbRoot.label }]} className="mb-3" />
        <h1 className="text-3xl font-bold">{selectedStylebookLabel}</h1>
        <p className="text-muted-foreground mt-2">
          Review data-quality issues and open records to fix them manually
        </p>
      </div>

      <StylebookHomeTabs />

      {loading ? (
        <div className="flex items-center gap-2 text-muted-foreground py-8">
          <Loader2 className="h-5 w-5 animate-spin" />
          Loading cleanup checks…
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {CLEANUP_CHECK_CONFIGS.map((config) => {
            const apiCheck = checksById.get(config.id)
            const count = apiCheck?.count ?? 0
            const href = `${catalogBasePath}/cleanup/${config.id}${catalogScopeSuffix}`
            return (
              <Link key={config.id} to={href} className="block">
                <Card className="h-full hover:shadow-lg transition-shadow cursor-pointer">
                  <CardHeader>
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <CardTitle>{config.title}</CardTitle>
                        <CardDescription className="mt-2">{config.description}</CardDescription>
                      </div>
                      <span
                        className={`text-2xl font-bold shrink-0 ${
                          count > 0 ? "text-orange-600" : "text-muted-foreground"
                        }`}
                      >
                        {count.toLocaleString()}
                      </span>
                    </div>
                  </CardHeader>
                  <CardContent>
                    <p className="text-sm text-muted-foreground">
                      {count === 1 ? "1 item to review" : `${count.toLocaleString()} items to review`}
                    </p>
                  </CardContent>
                </Card>
              </Link>
            )
          })}
        </div>
      )}
    </div>
  )
}
