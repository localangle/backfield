import { Plus } from "lucide-react"
import { cn } from "@/lib/utils"

/** Muted icon + label control used for “Add Workspace” / “Add Project” grid tiles. */
export function AddPlusCta({
  label,
  onClick,
  className,
  ariaLabel,
}: {
  label: string
  onClick: () => void
  className?: string
  /** Defaults to `label` */
  ariaLabel?: string
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex flex-col items-center justify-center gap-2 rounded-lg py-10 px-6 text-muted-foreground transition-colors hover:bg-muted/45 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        className,
      )}
      aria-label={ariaLabel ?? label}
    >
      <Plus className="h-8 w-8 shrink-0" aria-hidden />
      <span className="text-sm font-medium">{label}</span>
    </button>
  )
}
