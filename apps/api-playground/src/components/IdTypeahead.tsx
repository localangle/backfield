import { useEffect, useId, useState } from "react"
import { Search, X } from "lucide-react"

import { searchIdCandidates, type IdCandidate } from "../lib/api"
import type { TypeaheadKind } from "../lib/presentation"

interface IdTypeaheadProps {
  apiKey: string
  entityType?: string
  id: string
  kind: TypeaheadKind
  origin: string
  placeholder?: string
  projectSlug: string
  required?: boolean
  value: string
  onChange: (value: string) => void
}

function kindLabel(kind: TypeaheadKind): string {
  return kind[0].toUpperCase() + kind.slice(1)
}

export default function IdTypeahead({
  apiKey,
  entityType,
  id,
  kind,
  origin,
  placeholder,
  projectSlug,
  required,
  value,
  onChange,
}: IdTypeaheadProps) {
  const listId = useId()
  const [query, setQuery] = useState("")
  const [debouncedQuery, setDebouncedQuery] = useState("")
  const [candidates, setCandidates] = useState<IdCandidate[]>([])
  const [selected, setSelected] = useState<IdCandidate>()
  const [status, setStatus] = useState<"error" | "idle" | "loading" | "ready">("idle")
  const [open, setOpen] = useState(false)

  useEffect(() => {
    if (!value) {
      setSelected(undefined)
      setQuery("")
    }
  }, [value])

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedQuery(query.trim()), 200)
    return () => window.clearTimeout(timer)
  }, [query])

  useEffect(() => {
    if (
      debouncedQuery.length < 2 ||
      !projectSlug ||
      !apiKey ||
      selected
    ) {
      setCandidates([])
      setStatus("idle")
      return
    }
    const controller = new AbortController()
    setStatus("loading")
    void searchIdCandidates(
      origin,
      projectSlug,
      apiKey,
      kind,
      debouncedQuery,
      entityType,
      controller.signal,
    )
      .then((results) => {
        setCandidates(results)
        setStatus("ready")
      })
      .catch((caught: unknown) => {
        if (caught instanceof DOMException && caught.name === "AbortError") return
        setCandidates([])
        setStatus("error")
      })
    return () => controller.abort()
  }, [
    apiKey,
    debouncedQuery,
    entityType,
    kind,
    origin,
    projectSlug,
    selected,
  ])

  let helper = `Type at least 2 characters to search ${kindLabel(kind).toLowerCase()} records.`
  if (!projectSlug) helper = "Select a project first."
  else if (!apiKey) helper = "Enter an API key to search."
  else if (selected) helper = `Selected ID: ${selected.id}`
  else if (status === "loading") helper = "Searching…"
  else if (status === "error") helper = "Search is unavailable. Try again."

  const showResults =
    open &&
    debouncedQuery.length >= 2 &&
    Boolean(projectSlug) &&
    Boolean(apiKey) &&
    !selected

  return (
    <div className="id-typeahead">
      <div className="id-typeahead-input">
        <Search aria-hidden />
        <input
          id={id}
          role="combobox"
          aria-autocomplete="list"
          aria-expanded={showResults}
          aria-controls={listId}
          value={query}
          required={required}
          placeholder={placeholder}
          onFocus={() => setOpen(true)}
          onBlur={() => window.setTimeout(() => setOpen(false), 150)}
          onChange={(event) => {
            setQuery(event.target.value)
            setOpen(true)
            if (selected || value) {
              setSelected(undefined)
              onChange("")
            }
          }}
        />
      </div>
      <p className={`id-typeahead-helper ${status === "error" ? "error-message" : ""}`}>
        {helper}
      </p>

      {selected && (
        <div className="id-typeahead-selection">
          <span>
            <strong>{selected.label}</strong>
            <small>{selected.subtitle}</small>
          </span>
          <span className="id-typeahead-kind">{kindLabel(kind)}</span>
          <button
            type="button"
            aria-label={`Clear selected ${kind}`}
            onClick={() => {
              setSelected(undefined)
              setQuery("")
              onChange("")
            }}
          >
            <X aria-hidden />
          </button>
        </div>
      )}

      {showResults && (
        <ul id={listId} className="id-typeahead-results" role="listbox">
          {status === "loading" ? (
            <li className="id-typeahead-empty">Searching…</li>
          ) : candidates.length === 0 ? (
            <li className="id-typeahead-empty">No matches</li>
          ) : (
            candidates.map((candidate) => (
              <li key={candidate.id} role="option" aria-selected="false">
                <button
                  type="button"
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => {
                    setSelected(candidate)
                    setQuery(candidate.label)
                    setOpen(false)
                    onChange(candidate.id)
                  }}
                >
                  <span>
                    <strong>{candidate.label}</strong>
                    <small>{candidate.subtitle}</small>
                  </span>
                  <span className="id-typeahead-kind">{kindLabel(kind)}</span>
                </button>
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  )
}
