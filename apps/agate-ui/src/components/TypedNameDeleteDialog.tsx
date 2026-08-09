import type { ReactNode } from 'react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

export interface TypedNameDeleteDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description: string
  confirmLabel: string
  confirmName: string
  onConfirmNameChange: (value: string) => void
  expectedName: string
  loading?: boolean
  deleting?: boolean
  deleteButtonLabel: string
  deletingButtonLabel?: string
  children?: ReactNode
  onConfirm: () => void
}

export default function TypedNameDeleteDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel,
  confirmName,
  onConfirmNameChange,
  expectedName,
  loading = false,
  deleting = false,
  deleteButtonLabel,
  deletingButtonLabel = 'Deleting…',
  children,
  onConfirm,
}: TypedNameDeleteDialogProps) {
  const nameMatches = confirmName.trim() === expectedName.trim()

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        {loading ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : (
          <div className="space-y-4 text-sm">
            {children}
            <div className="space-y-2">
              <Label htmlFor="typed-name-delete-confirm">{confirmLabel}</Label>
              <Input
                id="typed-name-delete-confirm"
                value={confirmName}
                onChange={(e) => onConfirmNameChange(e.target.value)}
                autoComplete="off"
              />
            </div>
          </div>
        )}
        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={deleting}
          >
            Cancel
          </Button>
          <Button
            type="button"
            variant="destructive"
            onClick={onConfirm}
            disabled={deleting || loading || !nameMatches}
          >
            {deleting ? deletingButtonLabel : deleteButtonLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
