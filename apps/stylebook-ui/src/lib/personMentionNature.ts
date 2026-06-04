/** Person mention nature pill styling (Stylebook person canonical detail). */

const PERSON_NATURE_LABELS: Record<string, string> = {
  subject: "Subject",
  source: "Source",
  expert: "Expert",
  official: "Official",
  witness: "Witness",
  affected: "Affected",
  victim: "Victim",
  suspect: "Suspect",
  participant: "Participant",
  observer: "Observer",
  context: "Context",
  other: "Other",
}

const PERSON_NATURE_BADGE_CLASS: Record<string, string> = {
  subject: "border-violet-300 bg-violet-50 text-violet-800",
  source: "border-blue-300 bg-blue-50 text-blue-800",
  expert: "border-cyan-300 bg-cyan-50 text-cyan-800",
  official: "border-indigo-300 bg-indigo-50 text-indigo-800",
  witness: "border-amber-300 bg-amber-50 text-amber-800",
  affected: "border-orange-300 bg-orange-50 text-orange-800",
  victim: "border-rose-300 bg-rose-50 text-rose-800",
  suspect: "border-red-300 bg-red-50 text-red-800",
  participant: "border-teal-300 bg-teal-50 text-teal-800",
  observer: "border-slate-300 bg-slate-50 text-slate-700",
  context: "border-gray-300 bg-gray-50 text-gray-700",
  other: "border-gray-300 bg-gray-50 text-gray-600",
}

export function personNatureDisplayLabel(nature: string): string {
  const key = nature.trim().toLowerCase()
  return PERSON_NATURE_LABELS[key] ?? nature.replace(/_/g, " ")
}

export function personNatureBadgeClass(nature: string): string {
  const key = nature.trim().toLowerCase()
  return PERSON_NATURE_BADGE_CLASS[key] ?? "border-gray-300 bg-gray-50 text-gray-600"
}
