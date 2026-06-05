import type { ReactNode } from "react"
import type {
  CanonicalDetailConfig,
  CanonicalDetailSectionId,
  CanonicalMentionRow,
  CanonicalMentionSubstrate,
} from "@/lib/entityConfigs/canonicalDetailTypes"
import CanonicalMentionsSection, {
  type CanonicalMentionsSectionProps,
} from "@/components/CanonicalMentionsSection"
import ConnectionsSection from "@/components/ConnectionsSection"
import { Breadcrumbs, type BreadcrumbItem } from "@/components/Breadcrumbs"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Loader2, Trash2 } from "lucide-react"

export interface CanonicalDetailLayoutProps<
  TSubstrate extends CanonicalMentionSubstrate,
  TMention extends CanonicalMentionRow,
> {
  config: CanonicalDetailConfig<TSubstrate, TMention>
  breadcrumbs: BreadcrumbItem[]
  title: string
  loading?: boolean
  notFound?: ReactNode
  editing: boolean
  saving: boolean
  canEdit: boolean
  onStartEdit: () => void
  onCancelEdit: () => void
  onSave: () => void
  onDeleteClick: () => void
  deleteOpen: boolean
  onDeleteOpenChange: (open: boolean) => void
  deleting: boolean
  onDelete: () => void
  details: ReactNode
  geography?: ReactNode
  mentions: Omit<
    CanonicalMentionsSectionProps<TSubstrate, TMention>,
    "config"
  > & {
    config?: CanonicalMentionsSectionProps<TSubstrate, TMention>["config"]
  }
  meta?: ReactNode
  stylebookSlug?: string
  entityId?: string
  entityDisplayName?: string
  children?: ReactNode
}

function renderSection<
  TSubstrate extends CanonicalMentionSubstrate,
  TMention extends CanonicalMentionRow,
>(
  sectionId: CanonicalDetailSectionId,
  props: CanonicalDetailLayoutProps<TSubstrate, TMention>,
): ReactNode {
  switch (sectionId) {
    case "details":
      return props.details
    case "geography":
      return props.geography ?? null
    case "mentions":
      return (
        <CanonicalMentionsSection
          config={props.mentions.config ?? props.config.mentions}
          substrates={props.mentions.substrates}
          mentions={props.mentions.mentions}
          loading={props.mentions.loading}
          unlinkingId={props.mentions.unlinkingId}
          onUnlink={props.mentions.onUnlink}
          onMove={props.mentions.onMove}
        />
      )
    case "meta":
      return props.meta ?? null
    case "connections":
      if (!props.stylebookSlug || !props.entityId) return null
      return (
        <ConnectionsSection
          entityType={props.config.entityType}
          entityId={props.entityId}
          stylebookSlug={props.stylebookSlug}
          entityDisplayName={props.entityDisplayName ?? props.title}
        />
      )
    default:
      return null
  }
}

export default function CanonicalDetailLayout<
  TSubstrate extends CanonicalMentionSubstrate,
  TMention extends CanonicalMentionRow,
>(props: CanonicalDetailLayoutProps<TSubstrate, TMention>) {
  const {
    config,
    breadcrumbs,
    title,
    loading,
    notFound,
    editing,
    saving,
    canEdit,
    onStartEdit,
    onCancelEdit,
    onSave,
    onDeleteClick,
    deleteOpen,
    onDeleteOpenChange,
    deleting,
    onDelete,
    children,
  } = props

  if (loading) {
    return (
      <div className="flex justify-center items-center py-16">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (notFound) {
    return <>{notFound}</>
  }

  return (
    <div className="container mx-auto p-6 space-y-6">
      <div className="flex justify-between items-center">
        <div className="min-w-0">
          <Breadcrumbs className="mb-3" items={breadcrumbs} />
          <h1 className="text-3xl font-bold">{title}</h1>
        </div>
        <div className="flex gap-2">
          {editing ? (
            <>
              <Button variant="outline" onClick={onCancelEdit} disabled={saving}>
                Cancel
              </Button>
              <Button onClick={onSave} disabled={saving || !canEdit}>
                {saving ? "Saving…" : "Save"}
              </Button>
            </>
          ) : (
            <>
              <Button variant="outline" onClick={onStartEdit} disabled={!canEdit}>
                Edit
              </Button>
              <Button
                variant="destructive"
                size="icon"
                onClick={onDeleteClick}
                disabled={!canEdit}
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </>
          )}
        </div>
      </div>

      {config.sections.map((sectionId) => (
        <div key={sectionId}>{renderSection(sectionId, props)}</div>
      ))}

      <Dialog open={deleteOpen} onOpenChange={onDeleteOpenChange}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{config.deleteDialogTitle}</DialogTitle>
            <DialogDescription>{config.deleteDialogDescription(title)}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => onDeleteOpenChange(false)} disabled={deleting}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={() => void onDelete()} disabled={deleting}>
              {deleting ? "Deleting…" : "Delete"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {children}
    </div>
  )
}
