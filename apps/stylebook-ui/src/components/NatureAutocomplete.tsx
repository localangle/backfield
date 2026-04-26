import { useState, useRef, useEffect, useId, type KeyboardEvent } from "react"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { cn } from "@/lib/utils"

interface NatureAutocompleteProps {
  label: string
  value: string
  onChange: (value: string) => void
  suggestions: string[]
  placeholder?: string
  onSearchChange?: (value: string) => void
}

export default function NatureAutocomplete({
  label,
  value,
  onChange,
  suggestions,
  placeholder = "e.g. mayor, born in",
  onSearchChange,
}: NatureAutocompleteProps) {
  const id = useId()
  const [focused, setFocused] = useState(false)
  const [highlightIndex, setHighlightIndex] = useState(-1)
  const listRef = useRef<HTMLUListElement>(null)

  const showDropdown = focused && suggestions.length > 0
  const filteredSuggestions = suggestions.filter((s) =>
    s.toLowerCase().includes(value.toLowerCase().trim()),
  )

  useEffect(() => {
    setHighlightIndex(-1)
  }, [value, suggestions])

  useEffect(() => {
    if (
      showDropdown &&
      highlightIndex >= 0 &&
      highlightIndex < filteredSuggestions.length &&
      listRef.current
    ) {
      const el = listRef.current.children[highlightIndex] as HTMLElement
      el?.scrollIntoView({ block: "nearest" })
    }
  }, [highlightIndex, showDropdown, filteredSuggestions.length])

  const handleKeyDown = (e: KeyboardEvent) => {
    if (!showDropdown || filteredSuggestions.length === 0) {
      if (e.key === "Escape") setFocused(false)
      return
    }
    if (e.key === "ArrowDown") {
      e.preventDefault()
      setHighlightIndex((i) => Math.min(i + 1, filteredSuggestions.length - 1))
    } else if (e.key === "ArrowUp") {
      e.preventDefault()
      setHighlightIndex((i) => Math.max(i - 1, -1))
    } else if (
      e.key === "Enter" &&
      highlightIndex >= 0 &&
      highlightIndex < filteredSuggestions.length
    ) {
      e.preventDefault()
      onChange(filteredSuggestions[highlightIndex]!)
      setHighlightIndex(-1)
    } else if (e.key === "Escape") {
      setFocused(false)
      setHighlightIndex(-1)
    }
  }

  return (
    <div className="relative w-full">
      {label ? <Label htmlFor={id}>{label}</Label> : null}
      <Input
        id={id}
        value={value}
        onChange={(e) => {
          onChange(e.target.value)
          onSearchChange?.(e.target.value)
        }}
        onFocus={() => setFocused(true)}
        onBlur={() => {
          setTimeout(() => setFocused(false), 150)
        }}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
      />
      {showDropdown && filteredSuggestions.length > 0 && (
        <ul
          ref={listRef}
          className="absolute left-0 right-0 top-full z-50 mt-1 max-h-48 w-full overflow-auto rounded-md border bg-popover py-1 text-popover-foreground shadow-md"
          role="listbox"
        >
          {filteredSuggestions.map((suggestion, i) => (
            <li
              key={suggestion}
              role="option"
              aria-selected={i === highlightIndex}
              className={cn(
                "cursor-pointer px-3 py-2 text-sm",
                i === highlightIndex ? "bg-accent text-accent-foreground" : "hover:bg-accent/50",
              )}
              onMouseDown={(e) => {
                e.preventDefault()
                onChange(suggestion)
                setFocused(false)
              }}
            >
              {suggestion}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
