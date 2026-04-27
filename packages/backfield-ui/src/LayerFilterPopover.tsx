import * as DropdownMenu from "@radix-ui/react-dropdown-menu"
import { Layers } from "lucide-react"
import { cn } from "./cn"
import type { LayerOption, LayerVisibility } from "./layerVisibility"
import { hideAll, isLayerVisible, showAll, toggleLayer } from "./layerVisibility"

export type LayerFilterPopoverProps = {
  layers: LayerOption[]
  visibility: LayerVisibility
  onChange: (next: LayerVisibility) => void
  className?: string
  buttonLabel?: string
}

export function LayerFilterPopover({
  layers,
  visibility,
  onChange,
  className,
  buttonLabel = "Layers",
}: LayerFilterPopoverProps) {
  if (layers.length <= 1) return null

  return (
    <div className={cn("flex items-center justify-end", className)}>
      <DropdownMenu.Root>
        <DropdownMenu.Trigger asChild>
          <button
            type="button"
            className={cn(
              "inline-flex items-center gap-2 rounded-md border border-input bg-background px-3 py-2 text-sm",
              "hover:bg-accent hover:text-accent-foreground",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
            )}
          >
            <Layers className="h-4 w-4" />
            <span>{buttonLabel}</span>
          </button>
        </DropdownMenu.Trigger>

        <DropdownMenu.Portal>
          <DropdownMenu.Content
            sideOffset={8}
            align="end"
            className={cn(
              // Leaflet panes use high z-index values; ensure this renders above the map.
              "z-[2000] min-w-[15rem] overflow-hidden rounded-md border bg-popover p-1 text-popover-foreground shadow-md",
            )}
          >
            <div className="flex items-center justify-between gap-2 px-2 py-1.5">
              <div className="text-xs font-medium text-muted-foreground">Visible layers</div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  className="text-xs text-primary hover:underline"
                  onClick={() => onChange(showAll(layers))}
                >
                  Show all
                </button>
                <button
                  type="button"
                  className="text-xs text-primary hover:underline"
                  onClick={() => onChange(hideAll(layers))}
                >
                  Hide all
                </button>
              </div>
            </div>

            <DropdownMenu.Separator className="-mx-1 my-1 h-px bg-muted" />

            {layers.map((layer) => (
              <DropdownMenu.CheckboxItem
                key={layer.id}
                className={cn(
                  "relative flex cursor-default select-none items-center rounded-sm py-1.5 pl-8 pr-2 text-sm outline-none",
                  "transition-colors focus:bg-accent focus:text-accent-foreground",
                )}
                checked={isLayerVisible(visibility, layer.id)}
                onCheckedChange={() => onChange(toggleLayer(visibility, layer.id))}
              >
                <span className="absolute left-2 flex h-3.5 w-3.5 items-center justify-center">
                  <DropdownMenu.ItemIndicator>
                    <span className="text-xs">✓</span>
                  </DropdownMenu.ItemIndicator>
                </span>
                <span className="capitalize">{layer.label}</span>
              </DropdownMenu.CheckboxItem>
            ))}
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
      </DropdownMenu.Root>
    </div>
  )
}

