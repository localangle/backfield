import { useCallback, useEffect, useState } from "react"

export const CANONICAL_MENTIONS_PER_PAGE = 25

export interface PaginatedCanonicalMentionsResponse<TMention> {
  mentions: TMention[]
  total: number
}

export type FetchCanonicalMentionsPage<TMention> = (
  canonicalId: string,
  stylebookSlug: string,
  limit: number,
  offset: number,
  projectFilterSlug?: string,
) => Promise<PaginatedCanonicalMentionsResponse<TMention>>

export function usePaginatedCanonicalMentions<TMention>({
  canonicalId,
  stylebookSlug,
  projectFilterSlug,
  enabled,
  fetchPage,
}: {
  canonicalId: string | undefined
  stylebookSlug: string | undefined
  projectFilterSlug: string
  enabled: boolean
  fetchPage: FetchCanonicalMentionsPage<TMention>
}) {
  const [page, setPage] = useState(1)
  const [mentions, setMentions] = useState<TMention[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    setPage(1)
    setMentions([])
    setTotal(0)
  }, [canonicalId, stylebookSlug, projectFilterSlug])

  const loadPage = useCallback(
    async (pageNum: number, quiet = false) => {
      if (!canonicalId || !stylebookSlug) {
        setMentions([])
        setTotal(0)
        return
      }
      if (!quiet) setLoading(true)
      try {
        const offset = (pageNum - 1) * CANONICAL_MENTIONS_PER_PAGE
        const response = await fetchPage(
          canonicalId,
          stylebookSlug,
          CANONICAL_MENTIONS_PER_PAGE,
          offset,
          projectFilterSlug || undefined,
        )
        setMentions(response.mentions)
        setTotal(response.total)
        const totalPages = Math.max(
          1,
          Math.ceil(response.total / CANONICAL_MENTIONS_PER_PAGE),
        )
        if (pageNum > totalPages && response.total > 0) {
          setPage(totalPages)
        }
      } catch {
        setMentions([])
        setTotal(0)
      } finally {
        if (!quiet) setLoading(false)
      }
    },
    [canonicalId, stylebookSlug, projectFilterSlug, fetchPage],
  )

  useEffect(() => {
    if (!enabled || !canonicalId || !stylebookSlug) return
    void loadPage(page)
  }, [enabled, canonicalId, stylebookSlug, page, loadPage])

  const refreshMentions = useCallback(
    async (quiet = false) => {
      await loadPage(page, quiet)
    },
    [loadPage, page],
  )

  const clearMentions = useCallback(() => {
    setMentions([])
    setTotal(0)
    setPage(1)
  }, [])

  return {
    mentions,
    mentionTotal: total,
    mentionsPage: page,
    setMentionsPage: setPage,
    mentionsLoading: loading,
    refreshMentions,
    clearMentions,
    mentionsPerPage: CANONICAL_MENTIONS_PER_PAGE,
  }
}
