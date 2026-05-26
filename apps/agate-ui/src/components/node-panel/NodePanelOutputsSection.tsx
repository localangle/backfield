import type { ReactNode } from 'react'
import { Label } from '@/components/ui/label'

type NodePanelOutputsSectionProps = {
  title?: string
  children: ReactNode
}

/** Standard wrapper for run output content in the Outputs tab. */
export function NodePanelOutputsSection({
  title = 'Latest run',
  children,
}: NodePanelOutputsSectionProps) {
  return (
    <div className="space-y-2">
      <Label className="text-sm font-medium">{title}</Label>
      <div className="mt-2 space-y-2">{children}</div>
    </div>
  )
}

type JsonPreviewProps = {
  value: unknown
  maxHeightClassName?: string
}

export function NodePanelJsonPreview({ value, maxHeightClassName = 'max-h-48' }: JsonPreviewProps) {
  return (
    <div
      className={`text-xs font-mono p-2 bg-muted rounded overflow-y-auto whitespace-pre-wrap break-all ${maxHeightClassName}`}
    >
      {JSON.stringify(value, null, 2)}
    </div>
  )
}
