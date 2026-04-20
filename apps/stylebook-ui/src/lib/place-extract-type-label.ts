/** Human label for a PlaceExtract `location.type` value (snake_case → Title Case words). */
export function placeExtractTypeLabel(value: string): string {
  const v = value.trim()
  if (!v) return value
  return v
    .split("_")
    .map((part) => (part ? part.charAt(0).toUpperCase() + part.slice(1).toLowerCase() : ""))
    .filter(Boolean)
    .join(" ")
}
