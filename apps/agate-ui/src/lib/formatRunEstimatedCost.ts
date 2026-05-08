import type { Run } from '@/lib/api'

/** Show totals returned on ``Run`` from list/detail APIs (rollup of tracked LLM spend). */
export function formatRunEstimatedAiCost(run: Run): {
  display: string
  incomplete: boolean
} {
  const t = run.estimated_ai_cost_total
  const incomplete = Boolean(run.estimated_ai_cost_total_incomplete)
  const cur = run.whole_run_ai_cost_currency || 'USD'
  if (t === undefined || t === null) {
    return { display: '—', incomplete: false }
  }
  return {
    display: Number(t).toLocaleString(undefined, {
      style: 'currency',
      currency: cur,
      minimumFractionDigits: 2,
      maximumFractionDigits: 6,
    }),
    incomplete,
  }
}
