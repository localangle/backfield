import { useState, type ReactNode } from "react"
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
import { ChevronDown, Loader2, Trash2 } from "lucide-react"
import { cn } from "@/lib/utils"

interface AdvancedOptionsSectionProps {
  defaultOpen?: boolean
  children: ReactNode
}

function AdvancedOptionsSection({ defaultOpen = false, children }: AdvancedOptionsSectionProps) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="rounded-lg border bg-card text-card-foreground shadow-sm">
      <button
        type="button"
        className="flex w-full items-center justify-between gap-4 px-6 py-4 text-left transition-colors hover:bg-muted/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
        onClick={() => setOpen((prev) => !prev)}
        aria-expanded={open}
      >
        <span className="min-w-0 space-y-1">
          <span className="block text-xl font-semibold tracking-tight">Advanced options</span>
          <span className="block text-sm font-normal text-muted-foreground">
            Optional metadata and entity connections.
          </span>
        </span>
        <ChevronDown
          className={cn("h-5 w-5 shrink-0 text-muted-foreground transition-transform", open && "rotate-180")}
          aria-hidden
        />
      </button>
      {open ? <div className="space-y-4 border-t bg-muted/10 p-4">{children}</div> : null}
    </div>
  )
}

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
  topNotice?: ReactNode
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
          selectedSubstrateId={props.mentions.selectedSubstrateId}
          onSelectedSubstrateChange={props.mentions.onSelectedSubstrateChange}
          pagination={props.mentions.pagination}
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
    topNotice,
    children,
  } = props
  const firstAdvancedSectionId = config.sections.find((sectionId) =>
    sectionId === "meta" || sectionId === "connections",
  )

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

      {topNotice}

      {config.sections.map((sectionId) => {
        const section = renderSection(sectionId, props)
        if (!section) return null
        if (sectionId === "meta") {
          if (firstAdvancedSectionId !== "meta") return null
          const connectionsSection = renderSection("connections", props)
          return (
            <div key="advanced-options">
              <AdvancedOptionsSection>
                {section}
                {connectionsSection}
              </AdvancedOptionsSection>
            </div>
          )
        }
        if (sectionId === "connections") {
          if (firstAdvancedSectionId !== "connections") return null
          const metaSection = renderSection("meta", props)
          return (
            <div key="advanced-options">
              <AdvancedOptionsSection>
                {section}
                {metaSection}
              </AdvancedOptionsSection>
            </div>
          )
        }
        return <div key={sectionId}>{section}</div>
      })}

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
