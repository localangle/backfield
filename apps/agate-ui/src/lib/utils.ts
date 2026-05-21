import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

// Get timezone from environment variable, default to America/Chicago
const TIMEZONE = import.meta.env.VITE_TIMEZONE || 'America/Chicago'

/**
 * Format a date/timestamp string in the configured timezone
 * Assumes input timestamps are in UTC (as stored in database)
 */
export function formatDate(dateString: string, options?: {
  includeTime?: boolean
  dateStyle?: 'short' | 'medium' | 'long' | 'full'
  timeStyle?: 'short' | 'medium' | 'long' | 'full'
}): string {
  // Ensure we treat the input as UTC by appending 'Z' if not present
  let utcDateString = dateString
  if (!dateString.endsWith('Z') && !dateString.includes('+') && !dateString.includes('T')) {
    // If it's just a date, leave it as is
    utcDateString = dateString
  } else if (!dateString.endsWith('Z') && !dateString.includes('+')) {
    // Has time but no timezone indicator - append Z to treat as UTC
    utcDateString = dateString + 'Z'
  }
  
  const date = new Date(utcDateString)
  const {
    includeTime = true,
    dateStyle = 'medium',
    timeStyle = 'short'
  } = options || {}

  if (includeTime) {
    return date.toLocaleString('en-US', {
      timeZone: TIMEZONE,
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      hour12: true
    })
  } else {
    return date.toLocaleDateString('en-US', {
      timeZone: TIMEZONE,
      month: 'short',
      day: 'numeric',
      year: 'numeric'
    })
  }
}

// Backward compatibility alias
export const formatDateCentral = formatDate

/** Short date/time for run page titles and processed-item run links (e.g. "May 18, 2:30 PM"). */
export function formatRunTitleDate(dateString: string): string {
  const utcDateString =
    !dateString.endsWith('Z') && !dateString.includes('+') ? `${dateString}Z` : dateString
  const date = new Date(utcDateString)
  return date.toLocaleString('en-US', {
    timeZone: TIMEZONE,
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  })
}

