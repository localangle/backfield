export type CandidateQueueRequestToken = {
  scopeKey: string
  generation: number
}

export class CandidateQueueRequestGate {
  private scopeKey = ""
  private generation = 0

  setScope(scopeKey: string): void {
    if (scopeKey === this.scopeKey) return
    this.scopeKey = scopeKey
    this.generation += 1
  }

  begin(scopeKey: string): CandidateQueueRequestToken | null {
    if (scopeKey !== this.scopeKey) return null
    this.generation += 1
    return { scopeKey, generation: this.generation }
  }

  isCurrent(token: CandidateQueueRequestToken): boolean {
    return token.scopeKey === this.scopeKey && token.generation === this.generation
  }
}

export function updateCandidateProjectFilter(
  current: URLSearchParams,
  projectSlug: string,
): URLSearchParams {
  const next = new URLSearchParams(current)
  if (projectSlug === "all") next.delete("project")
  else next.set("project", projectSlug)
  return next
}

export function validCandidateTypeFilter(
  current: string,
  availableTypes: string[],
): string {
  if (current === "all" || availableTypes.includes(current)) return current
  return "all"
}
