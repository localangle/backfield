import { useCallback, useEffect, useMemo, useState } from "react"
import { useSearchParams } from "react-router-dom"
import { useProjectCatalogScope } from "@/lib/catalogNavigation"
import type { CanonicalListBaseUrlState } from "@/lib/entityConfigs/canonicalListTypes"

export type UseCanonicalListUrlStateOptions<
  TSort extends string,
  TUrlState extends CanonicalListBaseUrlState<TSort>,
> = {
  parseListArgs: (sp: URLSearchParams) => TUrlState
  extraDebouncedParamKeys?: string[]
  sortToUrlParam: (sort: TSort) => string | undefined
}

export function useCanonicalListUrlState<
  TSort extends string,
  TUrlState extends CanonicalListBaseUrlState<TSort>,
>(options: UseCanonicalListUrlStateOptions<TSort, TUrlState>) {
  const { parseListArgs, extraDebouncedParamKeys = [], sortToUrlParam } = options
  const { projectScopeSlug, projectFilterSlug } = useProjectCatalogScope()
  const [searchParams, setSearchParams] = useSearchParams()

  const urlState = useMemo(() => parseListArgs(searchParams), [parseListArgs, searchParams])

  const [searchQuery, setSearchQuery] = useState(() => searchParams.get("q") ?? "")
  const [textQueries, setTextQueries] = useState<Record<string, string>>(() => {
    const initial: Record<string, string> = {}
    for (const key of extraDebouncedParamKeys) {
      initial[key] = searchParams.get(key) ?? ""
    }
    return initial
  })

  useEffect(() => {
    setSearchQuery(searchParams.get("q") ?? "")
    setTextQueries((prev) => {
      const next = { ...prev }
      for (const key of extraDebouncedParamKeys) {
        next[key] = searchParams.get(key) ?? ""
      }
      return next
    })
  }, [searchParams, extraDebouncedParamKeys])

  useEffect(() => {
    const workflowScope = searchParams.get("project_scope")
    const inheritedProject = searchParams.get("project")
    if (workflowScope || !inheritedProject) return
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      const project = next.get("project")
      if (!project || next.get("project_scope")) return next
      next.set("project_scope", project)
      next.delete("project")
      return next
    }, { replace: true })
  }, [searchParams, setSearchParams])

  useEffect(() => {
    const urlQ = searchParams.get("q") ?? ""
    const timer = setTimeout(() => {
      if (searchQuery === urlQ) return
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev)
        const trimmed = searchQuery.trim()
        if (trimmed) next.set("q", trimmed)
        else next.delete("q")
        next.delete("page")
        return next
      })
    }, 300)
    return () => clearTimeout(timer)
  }, [searchQuery, searchParams, setSearchParams])

  useEffect(() => {
    const timers: ReturnType<typeof setTimeout>[] = []
    for (const key of extraDebouncedParamKeys) {
      const urlValue = searchParams.get(key) ?? ""
      const localValue = textQueries[key] ?? ""
      const timer = setTimeout(() => {
        if (localValue === urlValue) return
        setSearchParams((prev) => {
          const next = new URLSearchParams(prev)
          const trimmed = localValue.trim()
          if (trimmed) next.set(key, trimmed)
          else next.delete(key)
          next.delete("page")
          return next
        })
      }, 300)
      timers.push(timer)
    }
    return () => {
      for (const timer of timers) clearTimeout(timer)
    }
  }, [textQueries, extraDebouncedParamKeys, searchParams, setSearchParams])

  const setTextQuery = useCallback((key: string, value: string) => {
    setTextQueries((prev) => ({ ...prev, [key]: value }))
  }, [])

  const setSelectParam = useCallback(
    (key: string, value: string, omitWhen: string = "all") => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev)
        if (value === omitWhen) next.delete(key)
        else next.set(key, value)
        next.delete("page")
        return next
      })
    },
    [setSearchParams],
  )

  const setTypeFilterParam = useCallback(
    (value: string) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev)
        if (value === "all") next.delete("type")
        else next.set("type", value)
        next.delete("page")
        return next
      })
    },
    [setSearchParams],
  )

  const setProjectFilterParam = useCallback(
    (value: string) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev)
        if (value === "all-projects") next.delete("project")
        else {
          next.set("project", value)
          if (!next.get("project_scope")) {
            next.set("project_scope", projectScopeSlug || value)
          }
        }
        next.delete("page")
        return next
      })
    },
    [projectScopeSlug, setSearchParams],
  )

  const setSortParam = useCallback(
    (value: TSort) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev)
        const param = sortToUrlParam(value)
        if (param) next.set("sort", param)
        else next.delete("sort")
        next.delete("page")
        return next
      })
    },
    [setSearchParams, sortToUrlParam],
  )

  const setMinMentionsParam = useCallback(
    (n: number) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev)
        if (n <= 0) next.delete("min_mentions")
        else next.set("min_mentions", String(n))
        next.delete("page")
        return next
      })
    },
    [setSearchParams],
  )

  const setPageParam = useCallback(
    (page: number) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev)
        if (page <= 1) next.delete("page")
        else next.set("page", String(page))
        return next
      })
    },
    [setSearchParams],
  )

  return {
    searchParams,
    setSearchParams,
    urlState,
    searchQuery,
    setSearchQuery,
    textQueries,
    setTextQuery,
    setSelectParam,
    setTypeFilterParam,
    setProjectFilterParam,
    setSortParam,
    setMinMentionsParam,
    setPageParam,
    projectFilterSlug,
  }
}
