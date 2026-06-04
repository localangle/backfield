import { Button } from "@/components/ui/button"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { cn } from "@/lib/utils"
import { Link2, Loader2 } from "lucide-react"

export type LinkPickTableRow = {
  rowKey: string | number
  location: string
  typeLabel: string
  address: string
}

export function LinkPickTable(props: {
  rows: LinkPickTableRow[]
  busyKey?: string | number | null
  linkDisabled?: boolean
  onLink: (rowKey: string | number) => void
  /** Tooltip and aria-label for the link control */
  linkActionLabel?: string
  className?: string
  /** Primary column header (default Location for place candidates). */
  primaryColumnLabel?: string
  /** Secondary detail column header (default Address). */
  secondaryColumnLabel?: string
  /** When false, omit the secondary detail column (e.g. search where space is tight). */
  includeAddress?: boolean
  /** When false, omit the Type column (person link pickers). */
  includeType?: boolean
}) {
  const {
    rows,
    busyKey = null,
    linkDisabled = false,
    onLink,
    linkActionLabel = "Link",
    className,
    primaryColumnLabel = "Location",
    secondaryColumnLabel = "Address",
    includeAddress = true,
    includeType = true,
  } = props

  const primaryWidth = !includeType && !includeAddress
    ? "w-[62%]"
    : includeType && includeAddress
      ? "w-[34%]"
      : "w-[44%]"
  const typeWidth = includeAddress ? "w-[11%]" : "w-[26%]"

  if (rows.length === 0) return null

  return (
    <div className={cn("overflow-hidden rounded-md border", className)}>
      <Table className="table-fixed w-full">
        <TableHeader>
          <TableRow>
            <TableHead className={cn("min-w-0", primaryWidth)}>{primaryColumnLabel}</TableHead>
            {includeType ? (
              <TableHead className={cn("whitespace-nowrap", typeWidth)}>Type</TableHead>
            ) : null}
            {includeAddress ? (
              <TableHead className="min-w-0">{secondaryColumnLabel}</TableHead>
            ) : null}
            <TableHead className="w-14 text-right pr-2">
              <span className="sr-only">Actions</span>
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((r) => {
            const busy = busyKey === r.rowKey
            const disableOthers = busyKey !== null && busyKey !== undefined && !busy
            return (
              <TableRow key={String(r.rowKey)}>
                <TableCell className="min-w-0 py-3 align-middle font-medium break-words">
                  {r.location}
                </TableCell>
                {includeType ? (
                  <TableCell className="whitespace-nowrap py-3 align-middle text-sm text-muted-foreground">
                    {r.typeLabel}
                  </TableCell>
                ) : null}
                {includeAddress ? (
                  <TableCell className="min-w-0 py-3 align-middle text-sm text-muted-foreground break-words">
                    {r.address}
                  </TableCell>
                ) : null}
                <TableCell className="w-14 py-3 text-right align-middle">
                  <Button
                    type="button"
                    size="icon"
                    variant="default"
                    className="h-8 w-8 shrink-0"
                    title={linkActionLabel}
                    aria-label={linkActionLabel}
                    disabled={linkDisabled || busy || disableOthers}
                    onClick={() => onLink(r.rowKey)}
                  >
                    {busy ? (
                      <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                    ) : (
                      <Link2 className="h-4 w-4" aria-hidden />
                    )}
                  </Button>
                </TableCell>
              </TableRow>
            )
          })}
        </TableBody>
      </Table>
    </div>
  )
}
