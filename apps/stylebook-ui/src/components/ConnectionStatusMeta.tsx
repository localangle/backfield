import {
  formatConnectionStatusMeta,
  type ConnectionStatusMetaRow,
} from "@/lib/connectionEvidence"
import type { Connection } from "@/lib/stylebook-api/connections"
import { cn } from "@/lib/utils"

interface ConnectionStatusMetaProps {
  conn: Connection
  className?: string
  compact?: boolean
}

function StatusMetaList({
  rows,
  compact,
}: {
  rows: ConnectionStatusMetaRow[]
  compact?: boolean
}) {
  if (rows.length === 0) return null
  return (
    <dl
      className={cn(
        "grid gap-x-3 gap-y-1",
        compact ? "grid-cols-[auto_1fr] text-[11px]" : "grid-cols-[auto_1fr] text-xs",
      )}
    >
      {rows.map((row) => (
        <div key={row.label} className="contents">
          <dt className="text-muted-foreground">{row.label}</dt>
          <dd
            className={cn(
              "font-medium text-foreground",
              row.label === "Status" && row.value === "Closed" && "text-muted-foreground",
            )}
          >
            {row.value}
          </dd>
        </div>
      ))}
    </dl>
  )
}

export default function ConnectionStatusMeta({
  conn,
  className,
  compact = false,
}: ConnectionStatusMetaProps) {
  const rows = formatConnectionStatusMeta(conn)
  if (rows.length === 0) return null
  return (
    <div className={cn(compact ? "mt-1.5" : "mt-2", className)}>
      <StatusMetaList rows={rows} compact={compact} />
    </div>
  )
}
