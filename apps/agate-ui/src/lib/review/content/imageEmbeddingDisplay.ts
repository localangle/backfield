/** Read-only image embedding rows for processed item review. */

export interface ProcessedItemImageEmbeddingRow {
  url?: string | null
  base64?: string | null
  caption?: string | null
  generated_text?: string | null
  embedding_model?: string | null
  embedding_dimensions?: number | null
  vision_model?: string | null
}

function isImageEmbeddingRow(value: unknown): value is ProcessedItemImageEmbeddingRow {
  if (!value || typeof value !== 'object') return false
  const row = value as Record<string, unknown>
  return (
    'generated_text' in row &&
    'embedding_model' in row &&
    ('url' in row || 'base64' in row)
  )
}

function scanForImageEmbeddings(
  obj: unknown,
  results: ProcessedItemImageEmbeddingRow[],
): void {
  if (Array.isArray(obj)) {
    if (obj.length > 0 && obj.every(isImageEmbeddingRow)) {
      results.push(...obj)
      return
    }
    for (const item of obj) {
      scanForImageEmbeddings(item, results)
    }
    return
  }
  if (!obj || typeof obj !== 'object') return
  for (const value of Object.values(obj as Record<string, unknown>)) {
    if (Array.isArray(value) && value.length > 0 && value.every(isImageEmbeddingRow)) {
      results.push(...value)
    } else if (value && typeof value === 'object') {
      scanForImageEmbeddings(value, results)
    }
  }
}

export function collectProcessedItemImageEmbeddings(
  output: unknown,
): ProcessedItemImageEmbeddingRow[] {
  const rows: ProcessedItemImageEmbeddingRow[] = []
  scanForImageEmbeddings(output, rows)
  return rows
}

export function imageEmbeddingSource(row: ProcessedItemImageEmbeddingRow): string | null {
  const url = row.url
  if (typeof url === 'string' && url.trim()) return url.trim()
  const base64 = row.base64
  if (typeof base64 === 'string' && base64.trim()) return base64.trim()
  return null
}

export function formatImageEmbeddingModelDetail(row: ProcessedItemImageEmbeddingRow): string {
  const parts: string[] = []
  if (row.vision_model) parts.push(String(row.vision_model))
  if (row.embedding_model) {
    parts.push(String(row.embedding_model))
  }
  if (row.embedding_dimensions && row.embedding_dimensions > 0) {
    parts.push(`${row.embedding_dimensions} dimensions`)
  }
  return parts.join(' · ')
}
