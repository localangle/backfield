/** Organization mention nature pill styling (Stylebook organization canonical detail). */

const ORGANIZATION_NATURE_LABELS: Record<string, string> = {
  primary: "Primary",
  actor: "Actor",
  source: "Source",
  subject: "Subject",
  affected: "Affected",
  regulator: "Regulator",
  context: "Context",
  other: "Other",
}

const ORGANIZATION_NATURE_BADGE_CLASS: Record<string, string> = {
  primary: "border-violet-300 bg-violet-50 text-violet-800",
  actor: "border-indigo-300 bg-indigo-50 text-indigo-800",
  source: "border-blue-300 bg-blue-50 text-blue-800",
  subject: "border-purple-300 bg-purple-50 text-purple-800",
  affected: "border-orange-300 bg-orange-50 text-orange-800",
  regulator: "border-cyan-300 bg-cyan-50 text-cyan-800",
  context: "border-gray-300 bg-gray-50 text-gray-700",
  other: "border-gray-300 bg-gray-50 text-gray-600",
}

export function organizationNatureDisplayLabel(nature: string): string {
  const key = nature.trim().toLowerCase()
  return ORGANIZATION_NATURE_LABELS[key] ?? nature.replace(/_/g, " ")
}

export function organizationNatureBadgeClass(nature: string): string {
  const key = nature.trim().toLowerCase()
  return ORGANIZATION_NATURE_BADGE_CLASS[key] ?? "border-gray-300 bg-gray-50 text-gray-600"
}
