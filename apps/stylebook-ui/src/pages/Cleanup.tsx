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
  cleanupCheckStaleness,
  formatCleanupLastRun,
  formatCleanupStalenessLabel,
  loadCleanupHubState,
  type CleanupCheckRunRecord,
  type CleanupCheckStaleness,
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
  }, [storageKey])

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

      <div className="rounded-lg border overflow-hidden">
        <table className="w-full table-fixed text-sm">
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
        <div>{formatCleanupLastRun(lastRunAt)}</div>
        <CleanupStalenessIndicator
          staleness={cleanupCheckStaleness(lastRunAt)}
          label={formatCleanupStalenessLabel(lastRunAt)}
        />
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

const STALENESS_STYLES: Record<CleanupCheckStaleness, { dotClass: string; textClass: string }> = {
  fresh: { dotClass: "bg-green-500", textClass: "text-green-700" },
  aging: { dotClass: "bg-yellow-500", textClass: "text-yellow-700" },
  stale: { dotClass: "bg-red-500", textClass: "text-red-700" },
  never: { dotClass: "bg-red-500", textClass: "text-red-700" },
}

function CleanupStalenessIndicator({
  staleness,
  label,
}: {
  staleness: CleanupCheckStaleness
  label: string
}) {
  const { dotClass, textClass } = STALENESS_STYLES[staleness]
  return (
    <div className="mt-1 flex items-center gap-1.5">
      <span className={`inline-block h-2 w-2 shrink-0 rounded-full ${dotClass}`} aria-hidden />
      <span className={`text-xs ${textClass}`}>{label}</span>
    </div>
  )
}
