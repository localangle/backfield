import { Fragment, useMemo } from "react"
import { Link, useSearchParams } from "react-router-dom"
import { useProjectCatalogScope } from "@/lib/catalogNavigation"
import { useScopeBreadcrumbRoot } from "@/lib/breadcrumbs"
import { useSelectedStylebookLabel } from "@/lib/stylebookScopeContext"
import {
  candidatesWithSuggestedAction,
  suggestedActionShortLabel,
  suggestedRowAction,
} from "@/lib/candidateQueueSuggestions"
import { REVIEW_QUEUE_PAGE_SIZE, useCandidateQueuePage } from "@/lib/useCandidateQueuePage"
import type {
  CandidateQueuePageConfig,
  QueueCandidateBase,
} from "@/lib/entityConfigs/candidateQueueTypes"
import { CandidateQueueCreatedToast } from "@/components/CandidateQueueCreatedToast"
import { CandidateQueueLinkedToast } from "@/components/CandidateQueueLinkedToast"
import { CandidateQueueInlineNote } from "@/components/CandidateQueueInlineNote"
import { CreateCanonicalLinkNudgeAlert } from "@/components/CreateCanonicalLinkNudgeAlert"
import { PotentialCandidateLinksDialog } from "@/components/PotentialCandidateLinksDialog"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import Pagination from "@/components/Pagination"
import { cn } from "@/lib/utils"
import { Breadcrumbs } from "@/components/Breadcrumbs"
import {
  CandidateReviewReasons,
  candidateReviewLines,
} from "@/components/CandidateReviewReasons"
import {
  candidateQueueDataCellClass,
  resolveCandidateQueueColgroup,
} from "@/lib/candidateQueueTableLayout"
import { ChevronRight, Clock, Link2, Loader2, PlusCircle, StickyNote } from "lucide-react"

type CandidateQueuePageProps<TCandidate extends QueueCandidateBase> = {
  config: CandidateQueuePageConfig<TCandidate>
}

export function CandidateQueuePage<TCandidate extends QueueCandidateBase>({
  config,
}: CandidateQueuePageProps<TCandidate>) {
  const { catalogBasePath, filterScopeSuffix } = useProjectCatalogScope()
  const crumbRoot = useScopeBreadcrumbRoot()
  const stylebookLabel = useSelectedStylebookLabel()
  const [, setSearchParams] = useSearchParams()

  const page = useCandidateQueuePage(config)
  const {
    projectSlug,
    stylebookSlug,
    projects,
    projectsLoading,
    projectDisplayName,
    loading,
    listTotal,
    listPage,
    setListPage,
    listHasNext,
    listHasPrev,
    listTotalPages,
    candidates,
    status,
    setStatus,
    query,
    setQuery,
    typeFilter,
    setTypeFilter,
    orderedTypeFilterOptions,
    acceptingId,
    deferringId,
    linkingSuggestedId,
    acceptingAiRecommendations,
    linkModalId,
    linkModalInitialCanonicalId,
    linkModalSearchQuery,
    expandedId,
    contextById,
    contextLoadingId,
    createModalId,
    createDraft,
    createModalCandidate,
    createLinkNudge,
    error,
    queueToasts,
    candidateNotes,
    toggleExpanded,
    handleDefer,
    linkCandidateToSuggestedCanonical,
    acceptAiRecommendations,
    openCreateModal,
    closeCreateModal,
    submitCreateFromModal,
    openLinkModal,
    closeLinkModal,
    openLinkFromNudge,
    patchCreateDraft,
    refreshListQuiet,
  } = page

  const LinkModal = config.linkModal
  const columnCount = config.columns.length + 2
  const tableColgroup = resolveCandidateQueueColgroup(columnCount, config.tableLayout)
  const canonicalBasePath = `${catalogBasePath}/${config.entitySlug}/canonical`
  const suggestedCandidates = useMemo(
    () => candidatesWithSuggestedAction(candidates),
    [candidates],
  )
  const rowActionsBusy =
    acceptingAiRecommendations ||
    acceptingId !== null ||
    deferringId !== null ||
    linkingSuggestedId !== null

  return (
    <div className="container mx-auto p-6 space-y-6">
      {queueToasts.created.isVisible && queueToasts.created.payload ? (
        <CandidateQueueCreatedToast
          title={config.copy.createdToastTitle}
          canonicalHref={`${canonicalBasePath}/${queueToasts.created.payload.canonicalId}${filterScopeSuffix}`}
          canonicalLabel={queueToasts.created.payload.canonicalLabel}
          leaving={queueToasts.created.leaving}
          followupCheckingMessage={config.copy.followupCheckingMessage}
          followupLoading={queueToasts.followup.loading}
          followupError={queueToasts.followup.error}
          hasPotentialLinks={queueToasts.followup.hasMatches}
          onOpenPotentialLinks={queueToasts.followup.openPotentialLinks}
          onDismiss={queueToasts.created.dismissNow}
        />
      ) : null}
      {queueToasts.linked.isVisible && queueToasts.linked.payload ? (
        <CandidateQueueLinkedToast
          title={config.copy.linkedToastTitle}
          candidateLabel={queueToasts.linked.payload.candidateLabel}
          canonicalHref={`${canonicalBasePath}/${queueToasts.linked.payload.canonicalId}${filterScopeSuffix}`}
          canonicalLabel={queueToasts.linked.payload.canonicalLabel}
          leaving={queueToasts.linked.leaving}
          onDismiss={queueToasts.linked.dismissNow}
        />
      ) : null}

      <div className="flex justify-between items-center">
        <div className="min-w-0">
          <Breadcrumbs
            className="mb-3"
            items={[
              { label: crumbRoot.label, to: crumbRoot.to },
              {
                label: config.copy.breadcrumbEntityLabel,
                to: `${canonicalBasePath}${filterScopeSuffix}`,
              },
              { label: "Candidates" },
            ]}
          />
          <h1 className="text-3xl font-bold">{config.copy.pageTitle}</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Link candidates from{" "}
            <span className="font-semibold text-foreground">{projectDisplayName}</span> to Stylebook{" "}
            <span className="font-semibold text-foreground">{stylebookLabel}</span>
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="hidden sm:flex items-center gap-2">
            <Label className="text-sm text-muted-foreground">Project</Label>
            <Select
              value={projectSlug}
              onValueChange={(slug) => {
                setSearchParams((prev) => {
                  const next = new URLSearchParams(prev)
                  next.set("project_scope", slug)
                  return next
                })
              }}
              disabled={projectsLoading || projects.length === 0}
            >
              <SelectTrigger className="w-[16rem]">
                <SelectValue placeholder={projectsLoading ? "Loading…" : "Choose a project"} />
              </SelectTrigger>
              <SelectContent>
                {projects.map((p) => (
                  <SelectItem key={p.id} value={p.slug}>
                    {p.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Link to={`${canonicalBasePath}${filterScopeSuffix}`}>
            <Button variant="outline">{config.copy.canonicalButtonLabel}</Button>
          </Link>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Review queue</CardTitle>
          <CardDescription>{config.copy.reviewQueueDescription}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor={config.copy.searchInputId}>Search</Label>
            <Input
              id={config.copy.searchInputId}
              className={config.typeFilter ? "w-full max-w-none" : undefined}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={config.copy.searchPlaceholder}
            />
          </div>

          {config.typeFilter ? (
            <div className="flex flex-wrap gap-4 items-end justify-between">
              <div className="w-full max-w-xs">
                <Label>Type</Label>
                <Select value={typeFilter} onValueChange={setTypeFilter}>
                  <SelectTrigger>
                    <SelectValue placeholder="All types" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All</SelectItem>
                    {orderedTypeFilterOptions.map((opt) => (
                      <SelectItem key={opt.value} value={opt.value}>
                        {opt.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              {loading ? (
                <div className="flex items-center gap-2 text-sm text-muted-foreground pb-2">
                  <Loader2 className="h-4 w-4 animate-spin shrink-0" />
                  <span>Loading…</span>
                </div>
              ) : null}
            </div>
          ) : loading ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin shrink-0" />
              <span>Loading…</span>
            </div>
          ) : null}

          {error ? <p className="text-sm text-destructive">{error}</p> : null}

          {status === "open" && suggestedCandidates.length > 0 ? (
            <div className="flex justify-end">
              <Button
                type="button"
                size="sm"
                disabled={loading || rowActionsBusy}
                onClick={() => void acceptAiRecommendations()}
              >
                {acceptingAiRecommendations ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Accepting recommendations…
                  </>
                ) : (
                  `Accept AI recommendations (${suggestedCandidates.length})`
                )}
              </Button>
            </div>
          ) : null}

          <div className="rounded-md border">
            <div
              className="flex gap-8 border-b border-border bg-muted/20 px-4"
              role="tablist"
              aria-label="Review queue"
            >
              {(["open", "deferred"] as const).map((tab) => (
                <button
                  key={tab}
                  type="button"
                  role="tab"
                  aria-selected={status === tab}
                  disabled={loading}
                  className={cn(
                    "whitespace-nowrap border-b-2 -mb-px py-3 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:opacity-50",
                    status === tab
                      ? "border-primary text-foreground"
                      : "border-transparent text-muted-foreground hover:text-foreground",
                  )}
                  onClick={() => setStatus(tab)}
                >
                  {tab === "open" ? "For review" : "Deferred"}
                </button>
              ))}
            </div>
            <Table className="table-fixed w-full">
              <colgroup>
                {tableColgroup.map((col, i) => (
                  <col key={i} style={{ width: col.width }} />
                ))}
              </colgroup>
              <TableHeader>
                <TableRow>
                  <TableHead className="min-w-0">{config.copy.primaryColumnHeader}</TableHead>
                  {config.columns.map((col) => (
                    <TableHead key={col.id} className={cn("min-w-0", col.className)}>
                      {col.header}
                    </TableHead>
                  ))}
                  <TableHead className="min-w-0 text-right">
                    <span className="sr-only">Actions</span>
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {candidates.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={columnCount} className="text-muted-foreground">
                      {config.copy.emptyState}
                    </TableCell>
                  </TableRow>
                ) : (
                  candidates.map((c) => {
                    const savedNoteText = String(contextById[c.id]?.note ?? c.note ?? "").trim()
                    const rowSug = suggestedRowAction(c)
                    const rowSugLabel = suggestedActionShortLabel(c, config.copy.suggestionLabels)
                    const suggestedCanonicalId =
                      rowSug === "link" ? config.api.getSuggestedCanonicalId(c) ?? "" : ""
                    const actionLabels = config.copy.actionLabels
                    const linkTitle =
                      rowSug === "link" && suggestedCanonicalId
                        ? actionLabels.link.titleSuggestedWithId
                        : rowSug === "link"
                          ? actionLabels.link.titleSuggested
                          : actionLabels.link.titleDefault
                    const linkAriaLabel =
                      rowSug === "link" && suggestedCanonicalId
                        ? actionLabels.link.suggestedWithId
                        : actionLabels.link.default
                    const createTitle =
                      rowSug === "create_new"
                        ? actionLabels.create.titleSuggested
                        : actionLabels.create.titleDefault
                    const createAriaLabel =
                      acceptingId === c.id
                        ? actionLabels.create.creating
                        : actionLabels.create.default
                    const deferTitle =
                      rowSug === "defer"
                        ? actionLabels.defer.titleSuggested
                        : actionLabels.defer.titleDefault

                    return (
                      <Fragment key={c.id}>
                        <TableRow id={`candidate-row-${c.id}`}>
                          <TableCell className={cn("font-medium", candidateQueueDataCellClass)}>
                            <div className="flex flex-col items-start gap-1 min-w-0">
                              <div className="flex items-center gap-2 min-w-0 w-full">
                                <Button
                                  type="button"
                                  size="icon"
                                  variant="ghost"
                                  className="h-8 w-8 shrink-0 text-muted-foreground hover:text-foreground"
                                  onClick={() => void toggleExpanded(c)}
                                  disabled={contextLoadingId === c.id}
                                  aria-expanded={expandedId === c.id}
                                  aria-label={
                                    expandedId === c.id ? "Hide context" : "Show context"
                                  }
                                >
                                  {contextLoadingId === c.id ? (
                                    <Loader2 className="h-4 w-4 animate-spin" />
                                  ) : (
                                    <ChevronRight
                                      className={cn(
                                        "h-4 w-4 transition-transform duration-200",
                                        expandedId === c.id && "rotate-90",
                                      )}
                                      aria-hidden
                                    />
                                  )}
                                </Button>
                                <span
                                  className="min-w-0 flex-1 truncate"
                                  title={(c.suggested_name ?? "").trim() || undefined}
                                >
                                  {c.suggested_name || "—"}
                                </span>
                                {c.note ? (
                                  <StickyNote
                                    className="h-3.5 w-3.5 shrink-0 text-muted-foreground"
                                    aria-label="Has a note"
                                  />
                                ) : null}
                              </div>
                              {rowSugLabel ? (
                                <div className="flex flex-wrap items-center gap-2 pl-10">
                                  <Badge variant="secondary" className="font-normal">
                                    Suggested
                                  </Badge>
                                  <span className="text-xs text-muted-foreground">
                                    {rowSugLabel}
                                  </span>
                                </div>
                              ) : null}
                              <CandidateReviewReasons lines={candidateReviewLines(c)} />
                            </div>
                          </TableCell>
                          {config.columns.map((col) => (
                            <TableCell
                              key={col.id}
                              className={cn(candidateQueueDataCellClass, col.className)}
                            >
                              {col.render(c)}
                            </TableCell>
                          ))}
                          <TableCell className="text-right whitespace-nowrap align-top">
                            <div className="inline-flex flex-nowrap items-center justify-end gap-1.5 px-0.5">
                              <Button
                                type="button"
                                size="icon"
                                variant={rowSug === "link" ? "default" : "outline"}
                                className={cn(
                                  "h-8 w-8 shrink-0",
                                  rowSug === "link" &&
                                    "ring-2 ring-primary ring-offset-2 ring-offset-background shadow-sm",
                                )}
                                title={linkTitle}
                                aria-label={linkAriaLabel}
                                disabled={
                                  acceptingId === c.id ||
                                  deferringId === c.id ||
                                  linkingSuggestedId === c.id
                                }
                                onClick={() => {
                                  if (rowSug === "link" && suggestedCanonicalId) {
                                    void linkCandidateToSuggestedCanonical(c)
                                    return
                                  }
                                  openLinkModal(c)
                                }}
                              >
                                {linkingSuggestedId === c.id ? (
                                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                                ) : (
                                  <Link2 className="h-4 w-4" aria-hidden />
                                )}
                              </Button>
                              <Button
                                type="button"
                                size="icon"
                                variant={rowSug === "create_new" ? "default" : "secondary"}
                                className={cn(
                                  "h-8 w-8 shrink-0",
                                  rowSug === "create_new" &&
                                    "ring-2 ring-primary ring-offset-2 ring-offset-background shadow-sm",
                                )}
                                title={createTitle}
                                aria-label={createAriaLabel}
                                disabled={acceptingId === c.id || deferringId === c.id}
                                onClick={() => openCreateModal(c)}
                              >
                                {acceptingId === c.id ? (
                                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                                ) : (
                                  <PlusCircle className="h-4 w-4" aria-hidden />
                                )}
                              </Button>
                              {status === "open" ? (
                                <Button
                                  type="button"
                                  size="icon"
                                  variant={rowSug === "defer" ? "default" : "outline"}
                                  className={cn(
                                    "h-8 w-8 shrink-0",
                                    rowSug === "defer" &&
                                      "ring-2 ring-primary ring-offset-2 ring-offset-background shadow-sm",
                                  )}
                                  title={deferTitle}
                                  aria-label={actionLabels.defer.default}
                                  disabled={acceptingId === c.id || deferringId === c.id}
                                  onClick={() => void handleDefer(c)}
                                >
                                  {deferringId === c.id ? (
                                    <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                                  ) : (
                                    <Clock className="h-4 w-4" aria-hidden />
                                  )}
                                </Button>
                              ) : null}
                            </div>
                          </TableCell>
                        </TableRow>
                        {expandedId === c.id ? (
                          <TableRow>
                            <TableCell colSpan={columnCount} className="bg-muted/30 min-w-0">
                              <div className="space-y-3 py-2 break-words [overflow-wrap:anywhere]">
                                <div>
                                  <div className="text-sm font-medium">Context</div>
                                  {contextLoadingId === c.id ? (
                                    <div className="text-sm text-muted-foreground flex items-center gap-2 py-2">
                                      <Loader2 className="h-4 w-4 animate-spin" />
                                      Loading…
                                    </div>
                                  ) : (contextById[c.id]?.examples?.length ?? 0) === 0 ? (
                                    <div className="text-sm text-muted-foreground py-1">
                                      No article examples found.
                                    </div>
                                  ) : (
                                    <ul className="mt-1 space-y-1">
                                      {contextById[c.id].examples.map((ex) => (
                                        <li key={ex.article_id} className="text-sm">
                                          <span className="text-muted-foreground">
                                            {ex.article_headline ?? `Article ${ex.article_id}`}:
                                          </span>{" "}
                                          <span>{ex.text}</span>
                                        </li>
                                      ))}
                                    </ul>
                                  )}
                                </div>
                                <CandidateQueueInlineNote
                                  candidateId={c.id}
                                  savedNoteText={savedNoteText}
                                  isEditing={candidateNotes.noteEditingId === c.id}
                                  draft={candidateNotes.noteDraftById[c.id] ?? ""}
                                  saving={candidateNotes.noteSavingId === c.id}
                                  disabled={
                                    acceptingId === c.id ||
                                    deferringId === c.id ||
                                    linkingSuggestedId === c.id
                                  }
                                  onOpenEditor={() =>
                                    candidateNotes.openInlineNoteEditor(c.id, savedNoteText)
                                  }
                                  onDraftChange={(value) =>
                                    candidateNotes.setNoteDraftById((prev) => ({
                                      ...prev,
                                      [c.id]: value,
                                    }))
                                  }
                                  onSave={() => void candidateNotes.saveInlineNote(c.id)}
                                  onCancelEdit={() => candidateNotes.setNoteEditingId(null)}
                                />
                              </div>
                            </TableCell>
                          </TableRow>
                        ) : null}
                      </Fragment>
                    )
                  })
                )}
              </TableBody>
            </Table>
          </div>

          <Pagination
            page={listPage}
            perPage={REVIEW_QUEUE_PAGE_SIZE}
            total={listTotal}
            totalPages={listTotalPages}
            hasNext={listHasNext}
            hasPrev={listHasPrev}
            onPageChange={setListPage}
            className="pt-4"
            itemLabel="candidates"
          />
        </CardContent>
      </Card>

      <LinkModal
        open={linkModalId !== null}
        onOpenChange={(o) => {
          if (!o) closeLinkModal()
        }}
        projectSlug={projectSlug}
        stylebookSlug={stylebookSlug}
        substrateId={linkModalId}
        initialCanonicalId={linkModalInitialCanonicalId}
        initialSearchQuery={linkModalSearchQuery}
        title={config.copy.linkModalTitle}
        onLinked={({ id, label }) => {
          queueToasts.linked.show({
            canonicalId: id,
            canonicalLabel: label,
            candidateLabel:
              (candidates.find((row) => row.id === linkModalId)?.suggested_name ?? "").trim() ||
              (linkModalId != null
                ? config.copy.candidateFallbackLabel(linkModalId)
                : config.copy.candidateFallbackLabel(0)),
          })
        }}
        onDone={() => void refreshListQuiet()}
      />

      <Dialog
        open={createModalId !== null}
        onOpenChange={(open) => {
          if (!open && acceptingId === createModalId) return
          if (!open) closeCreateModal()
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{config.createDialog.title}</DialogTitle>
            <DialogDescription>
              {config.createDialog.description(stylebookLabel)}
            </DialogDescription>
          </DialogHeader>
          {createLinkNudge ? (
            <CreateCanonicalLinkNudgeAlert
              existingLabel={createLinkNudge.label}
              entityNoun={config.createDialog.entityNoun}
              disabled={createModalId === null}
              onOpenLinkFlow={openLinkFromNudge}
            />
          ) : null}
          <div className="space-y-4">
            {config.createDialog.renderFields({
              draft: createDraft,
              setDraft: patchCreateDraft,
              candidate: createModalCandidate,
              accepting: acceptingId === createModalId,
            })}
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              disabled={acceptingId === createModalId}
              onClick={() => closeCreateModal()}
            >
              Cancel
            </Button>
            <Button
              type="button"
              disabled={
                acceptingId === createModalId ||
                config.createDialog.validate(createDraft) !== null
              }
              onClick={() => void submitCreateFromModal()}
            >
              {acceptingId === createModalId
                ? config.createDialog.creatingLabel
                : config.createDialog.submitLabel}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <PotentialCandidateLinksDialog
        {...queueToasts.potentialLinksDialog}
        candidateNounPlural={config.copy.potentialLinks.candidateNounPlural}
        linkActionLabel={config.copy.potentialLinks.linkActionLabel}
        primaryColumnLabel={config.copy.potentialLinks.primaryColumnLabel}
        secondaryColumnLabel={config.copy.potentialLinks.secondaryColumnLabel}
        includeType={config.copy.potentialLinks.includeType}
        includeAddress={config.copy.potentialLinks.includeAddress}
      />
    </div>
  )
}
