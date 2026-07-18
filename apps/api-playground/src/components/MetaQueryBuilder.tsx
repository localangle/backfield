import { useEffect, useMemo, useRef, useState } from "react"
import { ChevronDown, Plus, X } from "lucide-react"

import { fetchArticleMetaTypes, fetchArticleMetaValues } from "../lib/api"
import {
  metaCategoryLabel,
  metaConditionsToText,
  newMetaConditionId,
  parseMetaClauses,
  type MetaCondition,
} from "../lib/metaClauses"

interface MetaQueryBuilderProps {
  origin: string
  projectSlug: string
  apiKey: string
  /** Newline-separated clause text, the canonical `meta` parameter value. */
  value: string
  onChange: (value: string) => void
}

function CategoryMultiSelect({
  conditionId,
  categories,
  selected,
  loading,
  onChange,
}: {
  conditionId: string
  categories: string[]
  selected: string[]
  loading: boolean
  onChange: (values: string[]) => void
}) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState("")
  const containerRef = useRef<HTMLDivElement>(null)
  const selectedSet = useMemo(() => new Set(selected), [selected])

  useEffect(() => {
    if (!open) return
    function closeOnOutsideClick(event: MouseEvent) {
      if (!containerRef.current?.contains(event.target as Node)) {
        setOpen(false)
      }
    }
    window.addEventListener("mousedown", closeOnOutsideClick)
    return () => window.removeEventListener("mousedown", closeOnOutsideClick)
  }, [open])

  const options = useMemo(() => {
    const all = [...new Set([...categories, ...selected])].sort((left, right) =>
      metaCategoryLabel(left).localeCompare(metaCategoryLabel(right)),
    )
    const needle = query.trim().toLowerCase()
    if (!needle) return all
    return all.filter(
      (option) =>
        option.toLowerCase().includes(needle) ||
        metaCategoryLabel(option).toLowerCase().includes(needle),
    )
  }, [categories, selected, query])

  const summary =
    selected.length === 0
      ? loading
        ? "Loading categories…"
        : "Whole type (any category)"
      : selected.length === 1
        ? metaCategoryLabel(selected[0])
        : `${selected.length} categories`

  return (
    <div className="meta-category-select" ref={containerRef}>
      <button
        type="button"
        className="meta-category-trigger"
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-label={`Categories for condition ${conditionId}`}
        onClick={() => setOpen((current) => !current)}
      >
        <span className={selected.length === 0 ? "meta-category-placeholder" : undefined}>
          {summary}
        </span>
        <ChevronDown className="meta-category-chevron" aria-hidden />
      </button>
      {open && (
        <div className="meta-category-panel">
          <input
            type="search"
            value={query}
            placeholder="Search categories"
            aria-label="Search categories"
            onChange={(event) => setQuery(event.target.value)}
          />
          <div className="meta-category-options" role="listbox" aria-multiselectable>
            {options.length === 0 ? (
              <p className="meta-category-empty">
                {loading ? "Loading categories…" : "No matching categories."}
              </p>
            ) : (
              options.map((option) => (
                <label key={option} className="meta-category-option">
                  <input
                    type="checkbox"
                    checked={selectedSet.has(option)}
                    onChange={() =>
                      onChange(
                        selectedSet.has(option)
                          ? selected.filter((current) => current !== option)
                          : [...selected, option],
                      )
                    }
                  />
                  <span>{metaCategoryLabel(option)}</span>
                </label>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export default function MetaQueryBuilder({
  origin,
  projectSlug,
  apiKey,
  value,
  onChange,
}: MetaQueryBuilderProps) {
  const [conditions, setConditions] = useState<MetaCondition[]>(() => parseMetaClauses(value))
  const [metaTypes, setMetaTypes] = useState<string[]>([])
  const [valuesByType, setValuesByType] = useState<Record<string, string[]>>({})
  const [loadingTypes, setLoadingTypes] = useState(false)
  const [loadError, setLoadError] = useState("")

  const canLoad = Boolean(origin && projectSlug && apiKey)

  // External resets (e.g. project changes clear the value) re-seed the rows.
  useEffect(() => {
    if (value === "" && conditions.length > 0) {
      setConditions([])
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value])

  useEffect(() => {
    if (!canLoad) {
      setMetaTypes([])
      setValuesByType({})
      setLoadError("")
      return
    }
    const controller = new AbortController()
    setLoadingTypes(true)
    setLoadError("")
    void fetchArticleMetaTypes(origin, projectSlug, apiKey, controller.signal)
      .then((types) => {
        setMetaTypes(types)
        setValuesByType({})
      })
      .catch((caught: unknown) => {
        if (caught instanceof DOMException && caught.name === "AbortError") return
        setMetaTypes([])
        setLoadError("Metadata types could not be loaded for this project.")
      })
      .finally(() => setLoadingTypes(false))
    return () => controller.abort()
  }, [apiKey, canLoad, origin, projectSlug])

  const neededTypes = useMemo(
    () =>
      [...new Set(conditions.map((condition) => condition.metaType))].filter(
        (metaType) => metaType && !(metaType in valuesByType),
      ),
    [conditions, valuesByType],
  )

  useEffect(() => {
    if (!canLoad || neededTypes.length === 0) return
    const controller = new AbortController()
    for (const metaType of neededTypes) {
      void fetchArticleMetaValues(origin, projectSlug, metaType, apiKey, controller.signal)
        .then((values) => {
          setValuesByType((current) => ({ ...current, [metaType]: values }))
        })
        .catch((caught: unknown) => {
          if (caught instanceof DOMException && caught.name === "AbortError") return
          setValuesByType((current) => ({ ...current, [metaType]: [] }))
        })
    }
    return () => controller.abort()
  }, [apiKey, canLoad, neededTypes, origin, projectSlug])

  function commit(next: MetaCondition[]) {
    setConditions(next)
    onChange(metaConditionsToText(next))
  }

  function addCondition() {
    commit([
      ...conditions,
      {
        id: newMetaConditionId(),
        metaType: metaTypes[0] ?? "",
        exclude: false,
        categories: [],
      },
    ])
  }

  if (!canLoad) {
    return (
      <p className="meta-builder-hint">
        {projectSlug
          ? "Enter an API key to build metadata filters."
          : "Select a project to build metadata filters."}
      </p>
    )
  }

  return (
    <div className="meta-builder">
      {loadError && <p className="meta-builder-hint">{loadError}</p>}
      {conditions.length === 0 && !loadError && (
        <p className="meta-builder-hint">
          No metadata conditions yet. Articles must match every condition you add; within one
          condition, any selected category counts.
        </p>
      )}
      {conditions.map((condition) => (
        <div key={condition.id} className="meta-condition-row">
          <select
            value={condition.metaType}
            aria-label="Metadata type"
            onChange={(event) =>
              commit(
                conditions.map((row) =>
                  row.id === condition.id
                    ? { ...row, metaType: event.target.value, categories: [] }
                    : row,
                ),
              )
            }
          >
            {loadingTypes && metaTypes.length === 0 && (
              <option value="">Loading types…</option>
            )}
            {condition.metaType && !metaTypes.includes(condition.metaType) && (
              <option value={condition.metaType}>
                {metaCategoryLabel(condition.metaType)}
              </option>
            )}
            {metaTypes.map((metaType) => (
              <option key={metaType} value={metaType}>
                {metaCategoryLabel(metaType)}
              </option>
            ))}
          </select>
          <select
            value={condition.exclude ? "is_not" : "is"}
            aria-label="Condition operator"
            onChange={(event) =>
              commit(
                conditions.map((row) =>
                  row.id === condition.id
                    ? { ...row, exclude: event.target.value === "is_not" }
                    : row,
                ),
              )
            }
          >
            <option value="is">is</option>
            <option value="is_not">is not</option>
          </select>
          <CategoryMultiSelect
            conditionId={condition.id}
            categories={valuesByType[condition.metaType] ?? []}
            selected={condition.categories}
            loading={condition.metaType !== "" && !(condition.metaType in valuesByType)}
            onChange={(categories) =>
              commit(
                conditions.map((row) =>
                  row.id === condition.id ? { ...row, categories } : row,
                ),
              )
            }
          />
          <button
            type="button"
            className="meta-condition-remove"
            aria-label="Remove condition"
            onClick={() => commit(conditions.filter((row) => row.id !== condition.id))}
          >
            <X aria-hidden />
          </button>
        </div>
      ))}
      <div className="meta-builder-footer">
        <button type="button" className="secondary-button meta-add-condition" onClick={addCondition}>
          <Plus aria-hidden />
          Add condition
        </button>
        {value && <code className="meta-clause-preview">{value.split("\n").join("  ·  ")}</code>}
      </div>
    </div>
  )
}
