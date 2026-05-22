import type { Run } from '@/lib/api'

export function formatCurrencySummary(value: number, currency: string): string {
  const formatter = new Intl.NumberFormat(undefined, {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })

  if (!Number.isFinite(value)) return '—'
  if (value <= 0) return formatter.format(0)
  if (value < 0.01) return `< ${formatter.format(0.01)}`

  const truncated = Math.trunc(value * 100) / 100
  return formatter.format(truncated)
}

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
    display: formatCurrencySummary(Number(t), cur),
    incomplete,
  }
}
