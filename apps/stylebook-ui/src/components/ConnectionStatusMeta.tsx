import { Badge } from "@/components/ui/badge"
import { formatConnectionStatusMeta } from "@/lib/connectionEvidence"
import type { Connection } from "@/lib/stylebook-api/connections"
import { cn } from "@/lib/utils"

interface ConnectionStatusMetaProps {
  conn: Connection
  className?: string
  compact?: boolean
}

export default function ConnectionStatusMeta({
  conn,
  className,
  compact = false,
}: ConnectionStatusMetaProps) {
  const rows = formatConnectionStatusMeta(conn)
  if (rows.length === 0) return null
  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-1.5",
        compact ? "mt-1.5" : "mt-2",
        className,
      )}
    >
      {rows.map((row) => (
        <Badge
          key={row.label}
          variant="secondary"
          className={cn(
            "h-5 gap-1 border-transparent px-1.5 font-normal",
            compact ? "text-[11px]" : "text-xs",
            row.label === "Status" && row.value === "Closed" && "text-muted-foreground",
          )}
        >
          <span className="text-muted-foreground">{row.label}</span>
          <span className="font-medium text-foreground">{row.value}</span>
        </Badge>
      ))}
    </div>
  )
}
