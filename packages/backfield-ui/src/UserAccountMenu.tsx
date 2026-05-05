import * as DropdownMenu from "@radix-ui/react-dropdown-menu"
import { CircleUserRound } from "lucide-react"

import { cn } from "./cn"

export interface UserAccountMenuProps {
  /** Shown in tooltip / aria; typically the user email. */
  userLabel?: string
  isOrgAdmin: boolean
  /** When omitted, the “Change password” item is hidden (e.g. Stylebook UI without that route). */
  onChangePassword?: () => void
  onLogout: () => void
  /** When set and `isOrgAdmin`, shows “Manage users”. */
  onManageUsers?: () => void
  /** When set and `isOrgAdmin`, shows “Manage stylebooks”. */
  onManageCatalogs?: () => void
  /** When set and `isOrgAdmin`, shows “AI models”. */
  onAiModelsSettings?: () => void
  className?: string
}

export function UserAccountMenu({
  userLabel,
  isOrgAdmin,
  onChangePassword,
  onLogout,
  onManageUsers,
  onManageCatalogs,
  onAiModelsSettings,
  className,
}: UserAccountMenuProps) {
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <button
          type="button"
          className={cn(
            "inline-flex h-9 w-9 items-center justify-center rounded-full border border-input bg-background text-muted-foreground shadow-sm transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
            className,
          )}
          aria-label={userLabel ? `Account menu for ${userLabel}` : "Account menu"}
          title={userLabel}
        >
          <CircleUserRound className="h-5 w-5" aria-hidden />
        </button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          className="z-[110] min-w-[12rem] overflow-hidden rounded-md border bg-popover p-1 text-popover-foreground shadow-md"
          sideOffset={6}
          align="end"
        >
          {userLabel ? (
            <div
              className="px-2 py-2 text-xs text-muted-foreground border-b border-border mb-1 -mx-1 -mt-1 truncate"
              title={userLabel}
            >
              {userLabel}
            </div>
          ) : null}
          {onChangePassword ? (
            <DropdownMenu.Item
              className="relative flex cursor-default select-none items-center rounded-sm px-2 py-1.5 text-sm outline-none transition-colors focus:bg-accent focus:text-accent-foreground data-[disabled]:pointer-events-none data-[disabled]:opacity-50"
              onSelect={(e: Event) => {
                e.preventDefault()
                onChangePassword()
              }}
            >
              Change password
            </DropdownMenu.Item>
          ) : null}
          {isOrgAdmin && onManageUsers ? (
            <DropdownMenu.Item
              className="relative flex cursor-default select-none items-center rounded-sm px-2 py-1.5 text-sm outline-none transition-colors focus:bg-accent focus:text-accent-foreground data-[disabled]:pointer-events-none data-[disabled]:opacity-50"
              onSelect={(e: Event) => {
                e.preventDefault()
                onManageUsers()
              }}
            >
              Manage users
            </DropdownMenu.Item>
          ) : null}
          {isOrgAdmin && onManageCatalogs ? (
            <DropdownMenu.Item
              className="relative flex cursor-default select-none items-center rounded-sm px-2 py-1.5 text-sm outline-none transition-colors focus:bg-accent focus:text-accent-foreground data-[disabled]:pointer-events-none data-[disabled]:opacity-50"
              onSelect={(e: Event) => {
                e.preventDefault()
                onManageCatalogs()
              }}
            >
              Manage stylebooks
            </DropdownMenu.Item>
          ) : null}
          {isOrgAdmin && onAiModelsSettings ? (
            <DropdownMenu.Item
              className="relative flex cursor-default select-none items-center rounded-sm px-2 py-1.5 text-sm outline-none transition-colors focus:bg-accent focus:text-accent-foreground data-[disabled]:pointer-events-none data-[disabled]:opacity-50"
              onSelect={(e: Event) => {
                e.preventDefault()
                onAiModelsSettings()
              }}
            >
              AI models
            </DropdownMenu.Item>
          ) : null}
          {onChangePassword ||
          (isOrgAdmin &&
            (onManageUsers || onManageCatalogs || onAiModelsSettings)) ? (
            <DropdownMenu.Separator className="-mx-1 my-1 h-px bg-muted" />
          ) : null}
          <DropdownMenu.Item
            className="relative flex cursor-default select-none items-center rounded-sm px-2 py-1.5 text-sm outline-none transition-colors focus:bg-accent focus:text-accent-foreground data-[disabled]:pointer-events-none data-[disabled]:opacity-50"
            onSelect={(e: Event) => {
              e.preventDefault()
              void onLogout()
            }}
          >
            Log out
          </DropdownMenu.Item>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  )
}
