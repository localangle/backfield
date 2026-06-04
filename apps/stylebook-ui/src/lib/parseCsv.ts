/** Parse one CSV field starting at index; returns value and next index. */
function parseCsvField(text: string, start: number): { value: string; next: number } {
  let i = start
  let value = ""

  if (text[i] === '"') {
    i++
    while (i < text.length) {
      const ch = text[i]!
      if (ch === '"') {
        if (text[i + 1] === '"') {
          value += '"'
          i += 2
          continue
        }
        i++
        break
      }
      value += ch
      i++
    }
    return { value, next: i }
  }

  while (i < text.length) {
    const ch = text[i]!
    if (ch === "," || ch === "\n" || ch === "\r") break
    value += ch
    i++
  }
  return { value, next: i }
}

/** Split CSV text into rows of raw string fields (RFC 4180-style). */
export function parseCsvRecords(text: string): string[][] {
  const records: string[][] = []
  let row: string[] = []
  let i = 0

  while (i <= text.length) {
    if (i === text.length) {
      if (row.length > 0 || records.length === 0) records.push(row)
      break
    }

    const ch = text[i]!
    if (ch === ",") {
      row.push("")
      i++
      continue
    }
    if (ch === "\r") {
      if (text[i + 1] === "\n") i++
      records.push(row)
      row = []
      i++
      continue
    }
    if (ch === "\n") {
      records.push(row)
      row = []
      i++
      continue
    }

    const { value, next } = parseCsvField(text, i)
    row.push(value)
    i = next
    if (i < text.length && text[i] === ",") i++
  }

  return records
}

/**
 * Parse CSV text into row objects keyed by header names.
 * Matches Python ``csv.DictReader`` behavior for typical Stylebook imports.
 */
export function parseCsvRows(csvContent: string): Record<string, string>[] {
  const records = parseCsvRecords(csvContent.trim())
  if (records.length === 0) return []

  const headers = records[0]!.map((h) => h.trim())
  const rows: Record<string, string>[] = []

  for (let rowIndex = 1; rowIndex < records.length; rowIndex++) {
    const values = records[rowIndex]!
    const row: Record<string, string> = {}
    headers.forEach((header, idx) => {
      row[header] = (values[idx] ?? "").trim()
    })
    if (Object.values(row).some((value) => value.length > 0)) {
      rows.push(row)
    }
  }

  return rows
}
