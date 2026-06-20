import { useCallback, useEffect, useMemo, useState } from "react"
import { Link } from "react-router-dom"
import { Breadcrumbs } from "@/components/Breadcrumbs"
import { StylebookHomeTabs } from "@/components/StylebookHomeTabs"
import { useAppMessage } from "@/components/AppMessageProvider"
import { Button } from "@/components/ui/button"
import { Loader2, Play } from "lucide-react"
import { useProjectCatalogScope } from "@/lib/catalogNavigation"
import { useScopeBreadcrumbRoot } from "@/lib/breadcrumbs"
import { useSelectedStylebookLabel } from "@/lib/stylebookScopeContext"
import {
  CLEANUP_CHECK_CONFIGS,
  cleanupEntityIcon,
  type CleanupCheckConfig,
} from "@/lib/cleanupChecks"
import {
  cleanupLastRunStorageKey,
  formatCleanupLastRun,
  loadCleanupHubState,
  type CleanupCheckRunRecord,
} from "@/lib/cleanupHubLastRun"
import { refreshPersistedCleanupCheckCount } from "@/lib/api"

type CheckRunSnapshot = {
  count: number | null
  loading: boolean
}

function runSnapshotsFromStore(
  store: Record<string, CleanupCheckRunRecord>,
): Record<string, CheckRunSnapshot> {
  return Object.fromEntries(
    CLEANUP_CHECK_CONFIGS.map((config) => {
      const record = store[config.id]
      return [
        config.id,
        {
          count: record ? record.count : null,
          loading: false,
        },
      ]
    }),
  )
}

export default function Cleanup() {
  const { showError } = useAppMessage()
  const { stylebookSlug, catalogBasePath, catalogScopeSuffix, projectFilterSlug } =
    useProjectCatalogScope()
  const crumbRoot = useScopeBreadcrumbRoot()
  const selectedStylebookLabel = useSelectedStylebookLabel()
  const storageKey = useMemo(
    () => cleanupLastRunStorageKey(stylebookSlug, projectFilterSlug || undefined),
    [stylebookSlug, projectFilterSlug],
  )
  const [lastRunByCheckId, setLastRunByCheckId] = useState<Record<string, string>>({})
  const [runSnapshots, setRunSnapshots] = useState<Record<string, CheckRunSnapshot>>(() =>
    runSnapshotsFromStore({}),
  )

  useEffect(() => {
    const { records, lastRunByCheckId: persistedLastRun } = loadCleanupHubState(storageKey)
    setLastRunByCheckId(persistedLastRun)
    setRunSnapshots(runSnapshotsFromStore(records))

    if (!stylebookSlug) return
    const checkIds = Object.keys(persistedLastRun)
    if (checkIds.length === 0) return

    setRunSnapshots((prev) => {
      const next = { ...prev }
      for (const checkId of checkIds) {
        next[checkId] = {
          count: records[checkId]?.count ?? prev[checkId]?.count ?? null,
          loading: true,
        }
      }
      return next
    })

    let cancelled = false
    void (async () => {
      await Promise.all(
        checkIds.map(async (checkId) => {
          try {
            const record = await refreshPersistedCleanupCheckCount({
              stylebookSlug,
              checkId,
              project: projectFilterSlug || undefined,
            })
            if (cancelled) return
            setRunSnapshots((prev) => ({
              ...prev,
              [checkId]: { count: record.count, loading: false },
            }))
            setLastRunByCheckId((prev) => ({ ...prev, [checkId]: record.ranAtIso }))
          } catch {
            if (!cancelled) {
              setRunSnapshots((prev) => ({
                ...prev,
                [checkId]: { ...prev[checkId], loading: false },
              }))
            }
          }
        }),
      )
    })()

    return () => {
      cancelled = true
    }
  }, [storageKey, stylebookSlug, projectFilterSlug])

  const runCheck = useCallback(
    async (checkId: string) => {
      if (!stylebookSlug) return
      setRunSnapshots((prev) => ({
        ...prev,
        [checkId]: { ...prev[checkId], loading: true },
      }))
      try {
        const record = await refreshPersistedCleanupCheckCount({
          stylebookSlug,
          checkId,
          project: projectFilterSlug || undefined,
        })
        setRunSnapshots((prev) => ({
          ...prev,
          [checkId]: { count: record.count, loading: false },
        }))
        const store = loadCleanupHubState(storageKey)
        setLastRunByCheckId(store.lastRunByCheckId)
      } catch (error) {
        setRunSnapshots((prev) => ({
          ...prev,
          [checkId]: { ...prev[checkId], loading: false },
        }))
        showError(error instanceof Error ? error.message : "Failed to run cleanup check")
      }
    },
    [stylebookSlug, projectFilterSlug, storageKey, showError],
  )

  const runAllChecks = useCallback(async () => {
    await Promise.all(CLEANUP_CHECK_CONFIGS.map((config) => runCheck(config.id)))
  }, [runCheck])

  const anyLoading = CLEANUP_CHECK_CONFIGS.some((config) => runSnapshots[config.id]?.loading)
  const allLoading = CLEANUP_CHECK_CONFIGS.every((config) => runSnapshots[config.id]?.loading)

  return (
    <div className="space-y-6">
      <div>
        <Breadcrumbs items={[{ label: crumbRoot.label }]} className="mb-3" />
        <h1 className="text-3xl font-bold">{selectedStylebookLabel}</h1>
        <p className="text-muted-foreground mt-2 max-w-3xl">
          These checks surface common issues in the curation of canonical objects. Run a check to
          count open items, then open it to review and fix records manually.
        </p>
      </div>

      <StylebookHomeTabs />

      <div className="flex items-center justify-end">
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={anyLoading}
          onClick={() => void runAllChecks()}
        >
          {allLoading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Play className="h-4 w-4" />
          )}
          <span className="ml-2">Run all checks</span>
        </Button>
      </div>

      <div className="rounded-lg border overflow-x-auto">
        <table className="w-full table-fixed text-sm min-w-[48rem]">
          <colgroup>
            <col style={{ width: "4%" }} />
            <col style={{ width: "34%" }} />
            <col style={{ width: "10%" }} />
            <col style={{ width: "16%" }} />
            <col style={{ width: "16%" }} />
          </colgroup>
          <thead className="bg-muted/50 text-left">
            <tr>
              <th className="px-4 py-3 font-medium" aria-label="Type" />
              <th className="px-4 py-3 font-medium">Check</th>
              <th className="px-4 py-3 font-medium text-right">Issues</th>
              <th className="px-4 py-3 font-medium">Last run</th>
              <th className="px-4 py-3 font-medium text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {CLEANUP_CHECK_CONFIGS.map((config) => (
              <CleanupCheckRow
                key={config.id}
                config={config}
                href={`${catalogBasePath}/cleanup/${config.id}${catalogScopeSuffix}`}
                snapshot={runSnapshots[config.id] ?? { count: null, loading: false }}
                lastRunAt={lastRunByCheckId[config.id]}
                onRun={() => void runCheck(config.id)}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function CleanupCheckRow({
  config,
  href,
  snapshot,
  lastRunAt,
  onRun,
}: {
  config: CleanupCheckConfig
  href: string
  snapshot: CheckRunSnapshot
  lastRunAt?: string
  onRun: () => void
}) {
  const Icon = cleanupEntityIcon(config.entityType)
  const hasRun = snapshot.count !== null
  const count = snapshot.count ?? 0

  return (
    <tr className="border-t hover:bg-muted/30">
      <td className="px-4 py-3 text-muted-foreground">
        <Icon className="h-4 w-4" aria-hidden />
        <span className="sr-only">
          {config.entityType === "person"
            ? "People"
            : config.entityType === "organization"
              ? "Organizations"
              : "Locations"}
        </span>
      </td>
      <td className="px-4 py-3 min-w-0">
        {hasRun && count > 0 ? (
          <Link
            to={href}
            className="font-medium text-primary hover:underline block truncate"
            title={config.title}
          >
            {config.title}
          </Link>
        ) : (
          <span className="font-medium block truncate" title={config.title}>
            {config.title}
          </span>
        )}
        <p className="text-muted-foreground mt-1 line-clamp-2">{config.description}</p>
      </td>
      <td className="px-4 py-3 text-right tabular-nums">
        {snapshot.loading ? (
          <span className="inline-flex items-center justify-end gap-2 text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
            <span className="sr-only">Running check</span>
          </span>
        ) : hasRun ? (
          <span className={count > 0 ? "font-semibold text-orange-600" : "text-muted-foreground"}>
            {count.toLocaleString()}
          </span>
        ) : (
          <span className="text-muted-foreground">—</span>
        )}
      </td>
      <td className="px-4 py-3 text-muted-foreground whitespace-nowrap">
        {formatCleanupLastRun(lastRunAt)}
      </td>
      <td className="px-4 py-3 text-right">
        <div className="inline-flex items-center gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={snapshot.loading}
            onClick={onRun}
          >
            {snapshot.loading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Play className="h-4 w-4" />
            )}
            <span className="ml-1.5">Run</span>
          </Button>
          <Button type="button" variant="ghost" size="sm" asChild>
            <Link to={href}>Review</Link>
          </Button>
        </div>
      </td>
    </tr>
  )
}
