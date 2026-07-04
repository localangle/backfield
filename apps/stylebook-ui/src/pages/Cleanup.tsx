import { useCallback, useEffect, useRef, useState } from "react"
import { Link, useLocation } from "react-router-dom"
import { Breadcrumbs } from "@/components/Breadcrumbs"
import { StylebookHomeTabs } from "@/components/StylebookHomeTabs"
import { useAppMessage } from "@/components/AppMessageProvider"
import { Button } from "@/components/ui/button"
import { Loader2, Play, Square } from "lucide-react"
import { useProjectCatalogScope } from "@/lib/catalogNavigation"
import { useScopeBreadcrumbRoot } from "@/lib/breadcrumbs"
import { useSelectedStylebookLabel } from "@/lib/stylebookScopeContext"
import {
  CLEANUP_CHECK_CONFIGS,
  cleanupEntityIcon,
  type CleanupCheckConfig,
} from "@/lib/cleanupChecks"
import {
  cleanupCheckStaleness,
  formatCleanupLastRun,
  formatCleanupStalenessLabel,
  type CleanupCheckStaleness,
} from "@/lib/cleanupHubLastRun"
import {
  cancelCleanupCheckRun,
  listCleanupChecks,
  pollCleanupCheckRun,
  startCleanupCheckRun,
  type CleanupCheck,
  type CleanupCheckRunStatus,
} from "@/lib/api"

type CheckRunSnapshot = {
  count: number | null
  loading: boolean
  status: CleanupCheckRunStatus
  lastRunAt?: string
  errorMessage?: string | null
}

function snapshotFromCheck(check: CleanupCheck): CheckRunSnapshot {
  const hasRun = check.status !== "never_run"
  return {
    count: hasRun ? check.count : null,
    loading: check.status === "queued" || check.status === "running",
    status: check.status,
    lastRunAt: check.completed_at ?? check.ran_at ?? undefined,
    errorMessage: check.error_message,
  }
}

function emptySnapshots(): Record<string, CheckRunSnapshot> {
  return Object.fromEntries(
    CLEANUP_CHECK_CONFIGS.map((config) => [
      config.id,
      { count: null, loading: false, status: "never_run" as const },
    ]),
  )
}

function applyChecksToSnapshots(checks: CleanupCheck[]): Record<string, CheckRunSnapshot> {
  const byId = Object.fromEntries(checks.map((check) => [check.id, snapshotFromCheck(check)]))
  return Object.fromEntries(
    CLEANUP_CHECK_CONFIGS.map((config) => [
      config.id,
      byId[config.id] ?? { count: null, loading: false, status: "never_run" as const },
    ]),
  )
}

export default function Cleanup() {
  const { showError } = useAppMessage()
  const { stylebookSlug, catalogBasePath, catalogScopeSuffix, projectFilterSlug } =
    useProjectCatalogScope()
  const crumbRoot = useScopeBreadcrumbRoot()
  const selectedStylebookLabel = useSelectedStylebookLabel()
  const location = useLocation()
  const [runSnapshots, setRunSnapshots] = useState<Record<string, CheckRunSnapshot>>(emptySnapshots)
  const [hubLoading, setHubLoading] = useState(true)
  const pollTokensRef = useRef<Record<string, number>>({})

  const loadHub = useCallback(async () => {
    if (!stylebookSlug) return
    setHubLoading(true)
    try {
      const response = await listCleanupChecks({
        stylebookSlug,
        project: projectFilterSlug || undefined,
      })
      setRunSnapshots(applyChecksToSnapshots(response.checks))
    } catch (error) {
      showError(error instanceof Error ? error.message : "Failed to load cleanup checks")
    } finally {
      setHubLoading(false)
    }
  }, [stylebookSlug, projectFilterSlug, showError])

  useEffect(() => {
    void loadHub()
  }, [loadHub, location.key])

  const pollRun = useCallback(
    async (checkId: string) => {
      if (!stylebookSlug) return
      const token = (pollTokensRef.current[checkId] ?? 0) + 1
      pollTokensRef.current[checkId] = token
      try {
        const run = await pollCleanupCheckRun({
          stylebookSlug,
          checkId,
          project: projectFilterSlug || undefined,
        })
        if (pollTokensRef.current[checkId] !== token) return
        const response = await listCleanupChecks({
          stylebookSlug,
          project: projectFilterSlug || undefined,
          checkId,
        })
        const check = response.checks[0]
        if (!check) return
        setRunSnapshots((prev) => ({
          ...prev,
          [checkId]: snapshotFromCheck(check),
        }))
        if (run.status === "failed" && run.error_message) {
          showError(run.error_message)
        }
      } catch (error) {
        if (pollTokensRef.current[checkId] !== token) return
        setRunSnapshots((prev) => ({
          ...prev,
          [checkId]: { ...prev[checkId], loading: false },
        }))
        showError(error instanceof Error ? error.message : "Failed to run cleanup check")
      }
    },
    [stylebookSlug, projectFilterSlug, showError],
  )

  const runCheck = useCallback(
    async (checkId: string) => {
      if (!stylebookSlug) return
      setRunSnapshots((prev) => ({
        ...prev,
        [checkId]: {
          ...prev[checkId],
          loading: true,
          status: "running",
          errorMessage: null,
        },
      }))
      try {
        await startCleanupCheckRun({
          stylebookSlug,
          checkId,
          project: projectFilterSlug || undefined,
        })
        await pollRun(checkId)
      } catch (error) {
        setRunSnapshots((prev) => ({
          ...prev,
          [checkId]: { ...prev[checkId], loading: false },
        }))
        showError(error instanceof Error ? error.message : "Failed to run cleanup check")
      }
    },
    [stylebookSlug, projectFilterSlug, pollRun, showError],
  )

  const stopCheck = useCallback(
    async (checkId: string) => {
      if (!stylebookSlug) return
      try {
        await cancelCleanupCheckRun({
          stylebookSlug,
          checkId,
          project: projectFilterSlug || undefined,
        })
        pollTokensRef.current[checkId] = (pollTokensRef.current[checkId] ?? 0) + 1
        setRunSnapshots((prev) => ({
          ...prev,
          [checkId]: { ...prev[checkId], loading: false, status: "cancelled" },
        }))
      } catch (error) {
        showError(error instanceof Error ? error.message : "Failed to stop cleanup check")
      }
    },
    [stylebookSlug, projectFilterSlug, showError],
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
            {hubLoading ? (
              <tr className="border-t">
                <td colSpan={5} className="px-4 py-8 text-center text-muted-foreground">
                  <span className="inline-flex items-center gap-2">
                    <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                    Loading checks…
                  </span>
                </td>
              </tr>
            ) : (
              CLEANUP_CHECK_CONFIGS.map((config) => (
                <CleanupCheckRow
                  key={config.id}
                  config={config}
                  href={`${catalogBasePath}/cleanup/${config.id}${catalogScopeSuffix}`}
                  snapshot={runSnapshots[config.id] ?? { count: null, loading: false, status: "never_run" }}
                  onRun={() => void runCheck(config.id)}
                  onStop={() => void stopCheck(config.id)}
                />
              ))
            )}
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
  onRun,
  onStop,
}: {
  config: CleanupCheckConfig
  href: string
  snapshot: CheckRunSnapshot
  onRun: () => void
  onStop: () => void
}) {
  const Icon = cleanupEntityIcon(config.entityType)
  const hasRun = snapshot.status !== "never_run"
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
        {snapshot.status === "failed" && snapshot.errorMessage ? (
          <p className="text-destructive mt-1 text-xs line-clamp-2">{snapshot.errorMessage}</p>
        ) : null}
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
        {snapshot.lastRunAt ? (
          <div>{formatCleanupLastRun(snapshot.lastRunAt)}</div>
        ) : null}
        <CleanupStalenessIndicator
          staleness={cleanupCheckStaleness(snapshot.lastRunAt)}
          label={formatCleanupStalenessLabel(snapshot.lastRunAt)}
        />
      </td>
      <td className="px-4 py-3 text-right">
        <div className="inline-flex items-center gap-2">
          {snapshot.loading ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={onStop}
            >
              <Square className="h-3.5 w-3.5" />
              <span className="ml-1.5">Stop</span>
            </Button>
          ) : (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={onRun}
            >
              <Play className="h-4 w-4" />
              <span className="ml-1.5">Run</span>
            </Button>
          )}
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
