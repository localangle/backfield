import BookendChooser from '@/components/flow-builder/BookendChooser'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

type BookendSwapDialogProps = {
  open: boolean
  kind: 'input' | 'output'
  selectedType?: string
  onOpenChange: (open: boolean) => void
  onSelect: (type: string) => void
}

export default function BookendSwapDialog({
  open,
  kind,
  selectedType,
  onOpenChange,
  onSelect,
}: BookendSwapDialogProps) {
  const title = kind === 'input' ? 'Change content source' : 'Change destination'
  const description =
    kind === 'input'
      ? 'Pick a different source type. Steps in your flow will stay connected.'
      : 'Pick a different destination type. Steps in your flow will stay connected.'

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <div className="py-2">
          <BookendChooser
            kind={kind}
            selectedType={selectedType}
            onSelect={(type) => {
              onSelect(type)
              onOpenChange(false)
            }}
          />
        </div>
      </DialogContent>
    </Dialog>
  )
}
