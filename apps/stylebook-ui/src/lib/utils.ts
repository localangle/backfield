import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

function locationParts(s: string): string[] {
  return s
    .toLowerCase()
    .trim()
    .split(/\s*,\s*/)
    .map((p) => p.trim())
    .filter(Boolean)
}

function isPrefixOf(partsA: string[], partsB: string[]): boolean {
  if (partsA.length > partsB.length) return false
  for (let i = 0; i < partsA.length; i++) {
    if (partsA[i] !== partsB[i]) return false
  }
  return true
}

/** String similarity for EntitySelector suggested matches (ported from agate stylebook-ui). */
export function stringSimilarity(str1: string, str2: string): number {
  const s1 = str1.toLowerCase().trim()
  const s2 = str2.toLowerCase().trim()

  if (s1 === s2) return 100
  if (s1.length === 0 || s2.length === 0) return 0

  const longer = s1.length > s2.length ? s1 : s2
  const shorter = s1.length > s2.length ? s2 : s1

  const parts1 = locationParts(str1)
  const parts2 = locationParts(str2)
  if (parts1.length > 0 && parts2.length > 0) {
    if (isPrefixOf(parts1, parts2) || isPrefixOf(parts2, parts1)) {
      const matchLen = Math.min(parts1.length, parts2.length)
      const totalLen = Math.max(parts1.length, parts2.length)
      return 70 + (matchLen / totalLen) * 25
    }
  }

  if (longer.includes(shorter)) {
    const ratio = (shorter.length / longer.length) * 100
    if (
      longer.startsWith(shorter) &&
      (longer.length === shorter.length || /[\s,]/.test(longer[shorter.length]!))
    ) {
      return Math.max(ratio, 85)
    }
    return ratio
  }

  const maxLen = Math.max(s1.length, s2.length)
  let matches = 0
  const minLen = Math.min(s1.length, s2.length)
  for (let i = 0; i < minLen; i++) {
    if (s1[i] === s2[i]) matches++
  }

  const words1 = s1.split(/\s+/).filter((w) => w.length > 2)
  const words2 = s2.split(/\s+/).filter((w) => w.length > 2)
  let wordMatches = 0
  for (const w1 of words1) {
    if (words2.some((w2) => w2.includes(w1) || w1.includes(w2))) wordMatches++
  }

  const charSimilarity = (matches / maxLen) * 100
  const wordSimilarity =
    words1.length > 0 && words2.length > 0
      ? (wordMatches / Math.max(words1.length, words2.length)) * 100
      : 0

  return Math.max(charSimilarity, wordSimilarity)
}
