/** Parsing and encoding for the repeatable `meta` filter clause grammar. */

export interface MetaCondition {
  id: string
  metaType: string
  exclude: boolean
  categories: string[]
}

let conditionSequence = 0

export function newMetaConditionId(): string {
  conditionSequence += 1
  return `meta-condition-${conditionSequence}`
}

/** Parse newline- or comma-separated `[!]type[:cat1|cat2]` tokens into conditions. */
export function parseMetaClauses(text: string): MetaCondition[] {
  return text
    .split(/[\n,]/)
    .map((token) => token.trim())
    .filter(Boolean)
    .map((token) => {
      const exclude = token.startsWith("!")
      const body = exclude ? token.slice(1) : token
      const separator = body.indexOf(":")
      const metaType = separator === -1 ? body : body.slice(0, separator)
      const categories =
        separator === -1
          ? []
          : body
              .slice(separator + 1)
              .split("|")
              .map((category) => category.trim())
              .filter(Boolean)
      return { id: newMetaConditionId(), metaType: metaType.trim(), exclude, categories }
    })
    .filter((condition) => condition.metaType !== "")
}

export function encodeMetaClause(condition: MetaCondition): string {
  const categories = condition.categories.filter(Boolean)
  const body =
    categories.length === 0
      ? condition.metaType
      : `${condition.metaType}:${categories.join("|")}`
  return condition.exclude ? `!${body}` : body
}

/** Encode conditions as newline-separated clause tokens (the `meta` textarea format). */
export function metaConditionsToText(conditions: MetaCondition[]): string {
  return conditions
    .filter((condition) => condition.metaType !== "")
    .map(encodeMetaClause)
    .join("\n")
}

/** Human-friendly label for a machine category value, e.g. `local_government` → `Local government`. */
export function metaCategoryLabel(value: string): string {
  const spaced = value.replace(/[_-]+/g, " ").trim()
  return spaced ? spaced.charAt(0).toUpperCase() + spaced.slice(1) : value
}
