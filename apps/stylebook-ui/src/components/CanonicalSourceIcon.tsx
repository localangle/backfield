import { Bot, User } from 'lucide-react'

interface CanonicalSourceIconProps {
  createdByUserId: number | null | undefined
  className?: string
}

/**
 * Shows agent (robot) vs human (person) icon for canonical creation source.
 * Works for any canonical type (location, person, future).
 */
export default function CanonicalSourceIcon({ createdByUserId, className }: CanonicalSourceIconProps) {
  const isAgent = createdByUserId == null || createdByUserId === undefined
  const tooltip = isAgent ? 'Created by agent' : 'Created by human'
  const Icon = isAgent ? Bot : User
  return (
    <span
      title={tooltip}
      className={className}
      role="img"
      aria-label={tooltip}
    >
      <Icon className="h-4 w-4 text-muted-foreground" />
    </span>
  )
}
