import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useProjectCatalogScope } from "@/lib/catalogNavigation"
import { fetchProjects, type Project } from "@/lib/api"
import { pickCreateLinkNudge, candidateQueueNameKey, duplicateCreateNewSummary } from "@/lib/candidateQueueSimilarity"
import { suggestedRowAction, candidatesWithSuggestedAction } from "@/lib/candidateQueueSuggestions"
import { useCandidateQueueToasts } from "@/lib/useCandidateQueueToasts"
import { useCandidateQueueInlineNote } from "@/lib/useCandidateQueueInlineNote"
import type {
  CandidateQueuePageConfig,
  CandidateQueueStatus,
  QueueCandidateBase,
} from "@/lib/entityConfigs/candidateQueueTypes"

export const REVIEW_QUEUE_PAGE_SIZE = 100

export function useCandidateQueuePage<TCandidate extends QueueCandidateBase>(
  config: CandidateQueuePageConfig<TCandidate>,
) {
  const {
    projectScopeSlug: projectSlug,
    stylebookSlug,
  } = useProjectCatalogScope()

  const [projects, setProjects] = useState<Project[]>([])
  const [projectsLoading, setProjectsLoading] = useState(true)
  const projectDisplayName = useMemo(() => {
    const row = projects.find((p) => p.slug === projectSlug)
    const name = row?.name?.trim()
    return name || projectSlug || "this project"
  }, [projects, projectSlug])

  const [loading, setLoading] = useState(false)
  const [listTotal, setListTotal] = useState(0)
  const [listPage, setListPage] = useState(1)
  const [listHasNext, setListHasNext] = useState(false)
  const [listHasPrev, setListHasPrev] = useState(false)
  const [listFetchGen, setListFetchGen] = useState(0)
  const filterKeySeenRef = useRef<string | null>(null)
  const [candidates, setCandidates] = useState<TCandidate[]>([])
  const [status, setStatus] = useState<CandidateQueueStatus>("open")
  const [query, setQuery] = useState("")
  const [debouncedQuery, setDebouncedQuery] = useState("")
  const [typeFilter, setTypeFilter] = useState<string>("all")
  const filterKey = useMemo(() => {
    const base = `${projectSlug}|${stylebookSlug}|${status}|${debouncedQuery}`
    return config.typeFilter ? `${base}|${typeFilter}` : base
  }, [projectSlug, stylebookSlug, status, debouncedQuery, typeFilter, config.typeFilter])
  const [types, setTypes] = useState<string[]>([])
  const [acceptingId, setAcceptingId] = useState<number | null>(null)
  const [deferringId, setDeferringId] = useState<number | null>(null)
  const [linkModalId, setLinkModalId] = useState<number | null>(null)
  const [linkModalInitialCanonicalId, setLinkModalInitialCanonicalId] = useState<string | null>(
    null,
  )
  const [linkModalSearchQuery, setLinkModalSearchQuery] = useState<string | null>(null)
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [contextById, setContextById] = useState<
    Record<number, Awaited<ReturnType<typeof config.api.getContext>>>
  >({})
  const [contextLoadingId, setContextLoadingId] = useState<number | null>(null)
  const [createModalId, setCreateModalId] = useState<number | null>(null)
  const [createDraft, setCreateDraft] = useState<Record<string, unknown>>({})
  const [error, setError] = useState<string | null>(null)
  const [createLinkNudge, setCreateLinkNudge] = useState<{
    canonicalId: string
    label: string
  } | null>(null)
  const [linkingSuggestedId, setLinkingSuggestedId] = useState<number | null>(null)
  const [acceptingAiRecommendations, setAcceptingAiRecommendations] = useState(false)
  const [clearingRecommendationId, setClearingRecommendationId] = useState<number | null>(null)
  const [queueRecommendationCount, setQueueRecommendationCount] = useState(0)

  const listTotalPages = useMemo(
    () => Math.max(1, Math.ceil(listTotal / REVIEW_QUEUE_PAGE_SIZE)),
    [listTotal],
  )

  const orderedTypeFilterOptions = useMemo(
    () => (config.typeFilter ? config.typeFilter.labelTypeOptions(types) : []),
    [config.typeFilter, types],
  )

  const getCandidateCreateDisplayName = useCallback(
    (candidate: TCandidate): string => {
      const draft = config.createDialog.initDraft(candidate)
      const fromDraft = config.createDialog.getDraftLabelForNudge(draft).trim()
      return fromDraft || (candidate.suggested_name ?? "").trim()
    },
    [config.createDialog],
  )

  const duplicateCreateNewOnPage = useMemo(
    () => duplicateCreateNewSummary(candidates, getCandidateCreateDisplayName),
    [candidates, getCandidateCreateDisplayName],
  )

  const duplicateCreateNewCountByNameKey = useMemo(() => {
    const counts = new Map<string, number>()
    for (const cluster of duplicateCreateNewOnPage.clusters) {
      counts.set(cluster.nameKey, cluster.count)
    }
    return counts
  }, [duplicateCreateNewOnPage])

  const createModalCandidate = useMemo(
    () => (createModalId === null ? undefined : candidates.find((x) => x.id === createModalId)),
    [candidates, createModalId],
  )

  useEffect(() => {
    let cancelled = false
    setProjectsLoading(true)
    void fetchProjects()
      .then((rows) => {
        if (!cancelled) setProjects(rows)
      })
      .catch(() => {
        if (!cancelled) setProjects([])
      })
      .finally(() => {
        if (!cancelled) setProjectsLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!projectSlug) {
      filterKeySeenRef.current = null
      return
    }
    if (filterKeySeenRef.current === null) {
      filterKeySeenRef.current = filterKey
      return
    }
    if (filterKeySeenRef.current === filterKey) return
    filterKeySeenRef.current = filterKey
    setListFetchGen((g) => g + 1)
    setListPage(1)
  }, [filterKey, projectSlug])

  useEffect(() => {
    const t = window.setTimeout(() => setDebouncedQuery(query), 250)
    return () => window.clearTimeout(t)
  }, [query])

  useEffect(() => {
    if (!config.api.listTypes || !projectSlug) return
    void (async () => {
      try {
        const res = await config.api.listTypes!(projectSlug, status)
        setTypes(res.types)
      } catch {
        setTypes([])
      }
    })()
  }, [config.api, projectSlug, status])

  const refreshListQuiet = useCallback(async () => {
    if (!projectSlug) return
    setError(null)
    const type_filter = config.typeFilter && typeFilter !== "all" ? typeFilter : undefined
    const q = debouncedQuery.trim() || undefined
    const offset = (listPage - 1) * REVIEW_QUEUE_PAGE_SIZE
    try {
      const res = await config.api.list(projectSlug, status, {
        limit: REVIEW_QUEUE_PAGE_SIZE,
        offset,
        type_filter,
        q,
      })
      setListTotal(res.total)
      setCandidates(res.candidates)
      setListHasNext(res.has_next)
      setListHasPrev(res.has_prev)
      if (res.candidates.length === 0 && res.total > 0 && offset >= REVIEW_QUEUE_PAGE_SIZE) {
        setListPage((p) => Math.max(1, p - 1))
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request failed")
    }
  }, [projectSlug, status, debouncedQuery, typeFilter, listPage, config.api, config.typeFilter])

  const fetchAllFilteredCandidates = useCallback(async (): Promise<TCandidate[]> => {
    if (!projectSlug) return []
    const type_filter = config.typeFilter && typeFilter !== "all" ? typeFilter : undefined
    const q = debouncedQuery.trim() || undefined
    const all: TCandidate[] = []
    let offset = 0
    while (true) {
      const res = await config.api.list(projectSlug, status, {
        limit: REVIEW_QUEUE_PAGE_SIZE,
        offset,
        type_filter,
        q,
      })
      all.push(...res.candidates)
      if (!res.has_next) break
      offset += REVIEW_QUEUE_PAGE_SIZE
    }
    return all
  }, [projectSlug, status, debouncedQuery, typeFilter, config.api, config.typeFilter])

  const fetchOpenCandidatesForLabel = useCallback(
    async (label: string) => {
      if (!projectSlug) return []
      const res = await config.api.list(projectSlug, "open", {
        limit: 100,
        offset: 0,
        q: label,
      })
      return res.candidates
    },
    [projectSlug, config.api],
  )

  const queueToasts = useCandidateQueueToasts<TCandidate>({
    projectSlug,
    fetchOpenCandidatesForLabel,
    getCandidateLabel: (c) => c.suggested_name ?? "",
    mapFollowupRow: config.mapFollowupRow,
    linkCandidateToCanonical: async (c, canonicalId) => {
      if (!projectSlug) return
      await config.api.linkToCanonical(c.id, projectSlug, canonicalId)
    },
    onAfterToastLink: refreshListQuiet,
  })

  const saveCandidateNote = useCallback(
    async (candidateId: number, note: string | null) => {
      if (!projectSlug) return
      setError(null)
      try {
        await config.api.updateNote(projectSlug, candidateId, note)
        setContextById((prev) => {
          const existing = prev[candidateId]
          if (!existing) return prev
          return { ...prev, [candidateId]: { ...existing, note } }
        })
        await refreshListQuiet()
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to save note")
      }
    },
    [projectSlug, refreshListQuiet, config.api],
  )

  const candidateNotes = useCandidateQueueInlineNote({ onSave: saveCandidateNote })

  useEffect(() => {
    if (!projectSlug) return
    let cancelled = false
    void (async () => {
      setLoading(true)
      setError(null)
      const type_filter = config.typeFilter && typeFilter !== "all" ? typeFilter : undefined
      const q = debouncedQuery.trim() || undefined
      const offset = (listPage - 1) * REVIEW_QUEUE_PAGE_SIZE
      try {
        const res = await config.api.list(projectSlug, status, {
          limit: REVIEW_QUEUE_PAGE_SIZE,
          offset,
          type_filter,
          q,
        })
        if (cancelled) return
        setListTotal(res.total)
        setCandidates(res.candidates)
        setListHasNext(res.has_next)
        setListHasPrev(res.has_prev)
        if (
          !cancelled &&
          res.candidates.length === 0 &&
          res.total > 0 &&
          offset >= REVIEW_QUEUE_PAGE_SIZE
        ) {
          setListPage((p) => Math.max(1, p - 1))
        }
      } catch (e) {
        if (cancelled) return
        setError(e instanceof Error ? e.message : "Request failed")
        setListTotal(0)
        setCandidates([])
        setListHasNext(false)
        setListHasPrev(false)
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [projectSlug, status, debouncedQuery, typeFilter, listPage, listFetchGen, config.api, config.typeFilter])

  useEffect(() => {
    if (!projectSlug || status !== "open" || listTotal === 0) {
      setQueueRecommendationCount(0)
      return
    }
    if (listTotal <= REVIEW_QUEUE_PAGE_SIZE) {
      return
    }
    let cancelled = false
    void (async () => {
      try {
        const all = await fetchAllFilteredCandidates()
        if (cancelled) return
        setQueueRecommendationCount(candidatesWithSuggestedAction(all).length)
      } catch {
        if (!cancelled) setQueueRecommendationCount(0)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [projectSlug, status, listTotal, filterKey, fetchAllFilteredCandidates])

  useEffect(() => {
    if (!projectSlug || status !== "open" || listTotal === 0) {
      return
    }
    if (listTotal > REVIEW_QUEUE_PAGE_SIZE) {
      return
    }
    setQueueRecommendationCount(candidatesWithSuggestedAction(candidates).length)
  }, [projectSlug, status, listTotal, candidates])

  const refreshCreateLinkNudge = useCallback(
    async (candidateId: number, draftLabel: string) => {
      if (!projectSlug) return
      const draft = draftLabel.trim()
      if (!draft) {
        setCreateLinkNudge(null)
        return
      }
      try {
        const res = await config.api.getSuggestedCanonicals(projectSlug, candidateId, 16)
        const nudge = pickCreateLinkNudge(res.suggestions, draft)
        setCreateLinkNudge(
          nudge ? { canonicalId: nudge.canonicalId, label: nudge.label } : null,
        )
      } catch {
        setCreateLinkNudge(null)
      }
    },
    [projectSlug, config.api],
  )

  useEffect(() => {
    if (createModalId === null || !projectSlug) return
    let cancelled = false
    const draft = config.createDialog.getDraftLabelForNudge(createDraft).trim()
    if (!draft) {
      setCreateLinkNudge(null)
      return
    }
    setCreateLinkNudge(null)
    const t = window.setTimeout(() => {
      void (async () => {
        if (!cancelled) await refreshCreateLinkNudge(createModalId, draft)
      })()
    }, 280)
    return () => {
      cancelled = true
      window.clearTimeout(t)
    }
  }, [createModalId, createDraft, projectSlug, refreshCreateLinkNudge, config.createDialog])

  const openCreateModal = useCallback(
    (candidate: TCandidate) => {
      setCreateModalId(candidate.id)
      setCreateDraft(config.createDialog.initDraft(candidate))
      setCreateLinkNudge(null)
    },
    [config.createDialog],
  )

  const closeCreateModal = useCallback(() => {
    setCreateModalId(null)
    setCreateDraft({})
    setCreateLinkNudge(null)
  }, [])

  const submitCreateFromModal = useCallback(async () => {
    if (!projectSlug || createModalId === null || !createModalCandidate) return
    const validationError = config.createDialog.validate(createDraft)
    if (validationError) {
      setError(validationError)
      return
    }
    setAcceptingId(createModalId)
    setError(null)
    try {
      const body = config.createDialog.buildAcceptBody(createDraft, createModalCandidate)
      const acceptRes = await config.api.acceptCreateNew(projectSlug, createModalId, body)
      await refreshListQuiet()
      closeCreateModal()
      const cid = acceptRes.canonicalId.trim()
      if (!cid) {
        setError(config.createDialog.acceptMissingIdError)
        return
      }
      const label = config.createDialog.getDraftLabelForNudge(createDraft).trim()
      queueToasts.created.show({ canonicalLabel: label, canonicalId: cid })
    } catch (e) {
      setError(e instanceof Error ? e.message : "Accept failed")
    } finally {
      setAcceptingId(null)
    }
  }, [
    projectSlug,
    createModalId,
    createModalCandidate,
    createDraft,
    config.createDialog,
    config.api,
    refreshListQuiet,
    closeCreateModal,
    queueToasts.created,
  ])

  const applySuggestedAction = useCallback(
    async (
      candidate: TCandidate,
      options?: { silent?: boolean; batchCreatedByNameKey?: Map<string, string> },
    ): Promise<boolean> => {
      if (!projectSlug) return false
      const action = suggestedRowAction(candidate)
      if (!action) return false

      if (action === "link") {
        const cid = config.api.getSuggestedCanonicalId(candidate)
        if (!cid) return false
        setLinkingSuggestedId(candidate.id)
        setError(null)
        try {
          await config.api.linkToCanonical(candidate.id, projectSlug, cid)
          if (!options?.silent) {
            let canonLabel = cid
            try {
              canonLabel = await config.api.getCanonicalLabel(cid, stylebookSlug, projectSlug)
            } catch {
              // ignore; fall back to id
            }
            queueToasts.linked.show({
              canonicalId: cid,
              canonicalLabel: canonLabel,
              candidateLabel:
                (candidate.suggested_name ?? "").trim() ||
                config.copy.candidateFallbackLabel(candidate.id),
            })
          }
          return true
        } catch (e) {
          if (!options?.silent) {
            setError(e instanceof Error ? e.message : "Link failed")
          }
          return false
        } finally {
          setLinkingSuggestedId(null)
        }
      }

      if (action === "defer") {
        setDeferringId(candidate.id)
        setError(null)
        try {
          await config.api.defer(projectSlug, candidate.id)
          return true
        } catch (e) {
          if (!options?.silent) {
            setError(e instanceof Error ? e.message : "Defer failed")
          }
          return false
        } finally {
          setDeferringId(null)
        }
      }

      const draft = config.createDialog.initDraft(candidate)
      const validationError = config.createDialog.validate(draft)
      if (validationError) return false

      const createDisplayName = getCandidateCreateDisplayName(candidate)
      const createNameKey = candidateQueueNameKey(createDisplayName)
      if (
        options?.batchCreatedByNameKey &&
        createNameKey &&
        options.batchCreatedByNameKey.has(createNameKey)
      ) {
        const cid = options.batchCreatedByNameKey.get(createNameKey)!
        setLinkingSuggestedId(candidate.id)
        setError(null)
        try {
          await config.api.linkToCanonical(candidate.id, projectSlug, cid)
          return true
        } catch (e) {
          if (!options?.silent) {
            setError(e instanceof Error ? e.message : "Link failed")
          }
          return false
        } finally {
          setLinkingSuggestedId(null)
        }
      }

      setAcceptingId(candidate.id)
      setError(null)
      try {
        const body = config.createDialog.buildAcceptBody(draft, candidate)
        const acceptRes = await config.api.acceptCreateNew(projectSlug, candidate.id, body)
        const cid = acceptRes.canonicalId.trim()
        if (
          options?.batchCreatedByNameKey &&
          createNameKey &&
          cid &&
          !options.batchCreatedByNameKey.has(createNameKey)
        ) {
          options.batchCreatedByNameKey.set(createNameKey, cid)
        }
        if (!options?.silent) {
          if (!cid) {
            setError(config.createDialog.acceptMissingIdError)
            return false
          }
          const label = config.createDialog.getDraftLabelForNudge(draft).trim()
          queueToasts.created.show({ canonicalLabel: label, canonicalId: cid })
        }
        return true
      } catch (e) {
        if (!options?.silent) {
          setError(e instanceof Error ? e.message : "Accept failed")
        }
        return false
      } finally {
        setAcceptingId(null)
      }
    },
    [
      projectSlug,
      stylebookSlug,
      config.api,
      config.createDialog,
      config.copy,
      getCandidateCreateDisplayName,
      queueToasts.linked,
      queueToasts.created,
    ],
  )

  const linkCandidateToSuggestedCanonical = useCallback(
    async (candidate: TCandidate) => {
      await applySuggestedAction(candidate)
      await refreshListQuiet()
    },
    [applySuggestedAction, refreshListQuiet],
  )

  const handleDefer = useCallback(
    async (candidate: TCandidate) => {
      if (!projectSlug) return
      setDeferringId(candidate.id)
      setError(null)
      try {
        await config.api.defer(projectSlug, candidate.id)
        await refreshListQuiet()
      } catch (e) {
        setError(e instanceof Error ? e.message : "Defer failed")
      } finally {
        setDeferringId(null)
      }
    },
    [projectSlug, config.api, refreshListQuiet],
  )

  const handleClearRecommendation = useCallback(
    async (candidate: TCandidate) => {
      if (!projectSlug) return
      setClearingRecommendationId(candidate.id)
      setError(null)
      try {
        await config.api.clearRecommendation(projectSlug, candidate.id)
        await refreshListQuiet()
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to clear recommendation")
      } finally {
        setClearingRecommendationId(null)
      }
    },
    [projectSlug, config.api, refreshListQuiet],
  )

  const acceptAiRecommendations = useCallback(async () => {
    if (!projectSlug || status !== "open") return

    setAcceptingAiRecommendations(true)
    setError(null)
    try {
      const allCandidates = await fetchAllFilteredCandidates()
      const targets = allCandidates.filter((candidate) => suggestedRowAction(candidate) !== null)
      if (targets.length === 0) return

      const batchCreatedByNameKey = new Map<string, string>()
      for (const candidate of targets) {
        await applySuggestedAction(candidate, { silent: true, batchCreatedByNameKey })
      }
      await refreshListQuiet()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to accept AI recommendations")
    } finally {
      setAcceptingAiRecommendations(false)
    }
  }, [
    projectSlug,
    status,
    fetchAllFilteredCandidates,
    applySuggestedAction,
    refreshListQuiet,
  ])

  const toggleExpanded = useCallback(
    async (candidate: TCandidate) => {
      if (!projectSlug) return
      const next = expandedId === candidate.id ? null : candidate.id
      setExpandedId(next)
      if (next === null) return
      if (contextById[next]) return
      setContextLoadingId(next)
      try {
        const ctx = await config.api.getContext(projectSlug, next, 3)
        setContextById((prev) => ({ ...prev, [next]: ctx }))
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load context")
      } finally {
        setContextLoadingId(null)
      }
    },
    [projectSlug, expandedId, contextById, config.api],
  )

  const openLinkModal = useCallback(
    (candidate: TCandidate) => {
      const extras = config.onOpenLinkModal?.(candidate) ?? {
        initialCanonicalId: null as string | null,
        initialSearchQuery: null as string | null | undefined,
      }
      setLinkModalId(candidate.id)
      setLinkModalInitialCanonicalId(extras.initialCanonicalId ?? null)
      setLinkModalSearchQuery(extras.initialSearchQuery ?? null)
    },
    [config],
  )

  const closeLinkModal = useCallback(() => {
    setLinkModalId(null)
    setLinkModalInitialCanonicalId(null)
    setLinkModalSearchQuery(null)
  }, [])

  const openLinkFromNudge = useCallback(() => {
    if (createModalId === null || !createLinkNudge) return
    setLinkModalId(createModalId)
    setLinkModalInitialCanonicalId(createLinkNudge.canonicalId)
    setLinkModalSearchQuery(null)
    closeCreateModal()
  }, [createModalId, createLinkNudge, closeCreateModal])

  const patchCreateDraft = useCallback((patch: Record<string, unknown>) => {
    setCreateDraft((prev) => ({ ...prev, ...patch }))
  }, [])

  return {
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
    duplicateCreateNewOnPage,
    duplicateCreateNewCountByNameKey,
    getCandidateCreateDisplayName,
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
    clearingRecommendationId,
    acceptingAiRecommendations,
    queueRecommendationCount,
    hasQueueRecommendations: queueRecommendationCount > 0,
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
    handleClearRecommendation,
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
  }
}
