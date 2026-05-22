/** Whether ``source_file`` is an external path (e.g. S3 key), not an inline ingress label. */
export function isBatchFileSource(sourceFile: string | null | undefined): boolean {
  return Boolean(sourceFile && !sourceFile.startsWith('inline:'))
}

/** Label for the Source column / item header — file name or a short text preview. */
export function processedItemSourceLabel(item: {
  source_file?: string | null
  input_preview?: string | null
}): string | null {
  if (isBatchFileSource(item.source_file)) {
    const path = item.source_file!
    return path.split('/').pop() || path
  }
  const preview = item.input_preview?.trim()
  return preview || null
}
