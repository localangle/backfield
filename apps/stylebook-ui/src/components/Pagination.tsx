import React from 'react'
import { Button } from '@/components/ui/button'
import { ChevronLeft, ChevronRight } from 'lucide-react'

export interface PaginationProps {
  page: number
  perPage: number
  total: number
  totalPages: number
  hasNext: boolean
  hasPrev: boolean
  onPageChange: (newPage: number) => void
  className?: string
  itemLabel?: string  // e.g., "clusters" or "candidates" (default: "candidates")
}

/**
 * Reusable pagination component
 */
export default function Pagination({
  page,
  perPage,
  total,
  totalPages,
  hasNext,
  hasPrev,
  onPageChange,
  className = '',
  itemLabel = 'candidates',
}: PaginationProps) {
  const safeTotal =
    typeof total === "number" && Number.isFinite(total) ? Math.max(0, total) : 0
  const safeTotalPages =
    typeof totalPages === "number" && Number.isFinite(totalPages)
      ? Math.max(1, totalPages)
      : Math.max(1, Math.ceil(safeTotal / perPage) || 1)

  if (safeTotalPages <= 1) return null

  const label = safeTotal === 1 ? itemLabel.slice(0, -1) : itemLabel

  return (
    <div className={`flex items-center justify-between ${className}`}>
      <div className="text-sm text-muted-foreground">
        Showing {((page - 1) * perPage) + 1} to{" "}
        {Math.min(page * perPage, safeTotal)} of{" "}
        {safeTotal} {label}
      </div>
      <div className="flex items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          onClick={() => onPageChange(page - 1)}
          disabled={!hasPrev}
        >
          <ChevronLeft className="h-4 w-4" />
          Previous
        </Button>
        <div className="text-sm text-muted-foreground">
          Page {page} of {safeTotalPages}
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => onPageChange(page + 1)}
          disabled={!hasNext}
        >
          Next
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>
    </div>
  )
}
