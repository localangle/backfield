import { Fragment, useMemo } from "react"
import type {
  CanonicalMentionRow,
  CanonicalMentionsSectionConfig,
  CanonicalMentionSubstrate,
} from "@/lib/entityConfigs/canonicalDetailTypes"
import { mentionArticleDisplayTitle, mentionArticleHref } from "@/lib/mentionArticleDisplay"
import { cn } from "@/lib/utils"
import Pagination from "@/components/Pagination"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Loader2 } from "lucide-react"

export interface CanonicalMentionsPagination {
  page: number
  perPage: number
  total: number
  onPageChange: (page: number) => void
}

export interface CanonicalMentionsSectionProps<
  TSubstrate extends CanonicalMentionSubstrate,
  TMention extends CanonicalMentionRow,
> {
  config: CanonicalMentionsSectionConfig<TSubstrate, TMention>
  substrates: TSubstrate[]
  mentions: TMention[]
  loading: boolean
  unlinkingId: number | null
  onUnlink: (substrate: TSubstrate) => void
  onMove: (substrate: TSubstrate) => void
  pagination?: CanonicalMentionsPagination
}

export default function CanonicalMentionsSection<
  TSubstrate extends CanonicalMentionSubstrate,
  TMention extends CanonicalMentionRow,
>({
  config,
  substrates,
  mentions,
  loading,
  unlinkingId,
  onUnlink,
  onMove,
  pagination,
}: CanonicalMentionsSectionProps<TSubstrate, TMention>) {
  const substratesById = useMemo(
    () => new Map(substrates.map((substrate) => [substrate.id, substrate])),
    [substrates],
  )

  const mentionsBySubstrateId = useMemo(() => {
    const map = new Map<number, TMention[]>()
    for (const row of mentions) {
      const sid = config.getMentionSubstrateId(row)
      const bucket = map.get(sid) ?? []
      bucket.push(row)
      map.set(sid, bucket)
    }
    return map
  }, [config, mentions])

  const mentionTotal = pagination?.total ?? mentions.length
  const displaySubstrates = useMemo(() => {
    if (mentionTotal > 0) {
      const orderedIds: number[] = []
      const seen = new Set<number>()
      for (const row of mentions) {
        const sid = config.getMentionSubstrateId(row)
        if (seen.has(sid)) continue
        seen.add(sid)
        orderedIds.push(sid)
      }
      return orderedIds
        .map((id) => substratesById.get(id))
        .filter((substrate): substrate is TSubstrate => substrate != null)
    }
    return substrates
  }, [config, mentionTotal, mentions, substrates, substratesById])

  const totalPages = pagination
    ? Math.max(1, Math.ceil(pagination.total / pagination.perPage))
    : 1

  return (
    <Card className="relative z-10">
      <CardHeader>
        <CardTitle>Mentions</CardTitle>
        <CardDescription>{config.description}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {loading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground py-4">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading…
          </div>
        ) : substrates.length === 0 && mentionTotal === 0 ? (
          <p className="text-sm text-muted-foreground">{config.noLinkedMentionsMessage}</p>
        ) : (
          <>
            <div className="w-full overflow-x-auto">
              <Table className="w-full min-w-[56rem]">
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-[26%] min-w-[9rem]">
                      {config.columnHeaders.substrateArticle}
                    </TableHead>
                    <TableHead className="w-[6.5rem] min-w-[5.5rem]">
                      {config.columnHeaders.nature}
                    </TableHead>
                    <TableHead className="w-[10rem] min-w-[10rem]">
                      {config.columnHeaders.role}
                    </TableHead>
                    <TableHead className="min-w-[18rem]">{config.columnHeaders.quotedText}</TableHead>
                    <TableHead className="w-[12rem] min-w-[12rem] text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {displaySubstrates.map((s) => {
                    const group = mentionsBySubstrateId.get(s.id) ?? []
                    return (
                      <Fragment key={`group-${s.id}`}>
                        <TableRow className="bg-muted/50 border-t">
                          <TableCell colSpan={4} className="align-top py-3">
                            <div className="flex items-center gap-2 min-w-0">
                              <div className="font-medium min-w-0 break-words">{s.name}</div>
                              {config.renderSubstrateHeaderExtra?.(s)}
                            </div>
                            <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground break-words">
                              <Badge variant="outline" className="font-normal">
                                Project: {s.project_name}
                              </Badge>
                              {config.renderSubstrateSubtitle(s)}
                            </div>
                          </TableCell>
                          <TableCell className="text-right align-top py-3 w-[12rem] min-w-[12rem]">
                            <div className="flex flex-wrap justify-end gap-2">
                              <Button
                                type="button"
                                size="sm"
                                variant="outline"
                                className="relative z-10 shrink-0"
                                disabled={unlinkingId === s.id}
                                onClick={() => onMove(s)}
                              >
                                Move…
                              </Button>
                              <Button
                                type="button"
                                size="sm"
                                variant="secondary"
                                className="relative z-10 shrink-0"
                                disabled={unlinkingId === s.id}
                                onClick={() => onUnlink(s)}
                              >
                                {unlinkingId === s.id ? "Unlinking…" : "Unlink"}
                              </Button>
                            </div>
                          </TableCell>
                        </TableRow>
                        {group.length === 0 ? (
                          <TableRow>
                            <TableCell
                              colSpan={5}
                              className="pl-8 text-sm text-muted-foreground py-2"
                            >
                              {config.emptySubstrateMentionsMessage}
                            </TableCell>
                          </TableRow>
                        ) : (
                          group.map((m) => {
                            const articleHref = mentionArticleHref(m)
                            const articleLabel = mentionArticleDisplayTitle(m)
                            return (
                              <TableRow key={m.mention_id} className="hover:bg-muted/30">
                                <TableCell className="pl-8 align-top min-w-0">
                                  <div className="flex items-start gap-1 min-w-0">
                                    <span
                                      className="text-muted-foreground select-none shrink-0 pt-0.5"
                                      aria-hidden
                                    >
                                      ↳
                                    </span>
                                    <div className="min-w-0">
                                      {articleHref ? (
                                        <a
                                          href={articleHref}
                                          className="font-medium text-primary hover:underline break-words"
                                          target="_blank"
                                          rel="noopener noreferrer"
                                          title={articleLabel}
                                        >
                                          {articleLabel}
                                        </a>
                                      ) : (
                                        <span className="font-medium break-words" title={articleLabel}>
                                          {articleLabel}
                                        </span>
                                      )}
                                    </div>
                                  </div>
                                </TableCell>
                                <TableCell className="align-top py-3">
                                  <Badge
                                    variant="outline"
                                    className={cn(
                                      "font-medium shadow-none",
                                      config.getMentionNatureBadgeClass(m.mention_nature),
                                    )}
                                  >
                                    {config.getMentionNatureLabel(m.mention_nature)}
                                  </Badge>
                                </TableCell>
                                <TableCell className="text-muted-foreground text-sm align-top max-w-[10rem] break-words leading-snug">
                                  {m.description ?? "—"}
                                </TableCell>
                                <TableCell className="min-w-0 text-sm align-top break-words leading-relaxed">
                                  {m.original_text ?? "—"}
                                </TableCell>
                                <TableCell className="align-top" />
                              </TableRow>
                            )
                          })
                        )}
                      </Fragment>
                    )
                  })}
                </TableBody>
              </Table>
            </div>
            {pagination ? (
              <Pagination
                page={pagination.page}
                perPage={pagination.perPage}
                total={pagination.total}
                totalPages={totalPages}
                hasNext={pagination.page < totalPages}
                hasPrev={pagination.page > 1}
                onPageChange={pagination.onPageChange}
                itemLabel="mentions"
              />
            ) : null}
          </>
        )}
      </CardContent>
    </Card>
  )
}
