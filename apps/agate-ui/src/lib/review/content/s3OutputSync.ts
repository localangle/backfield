/** Detect S3 Output uploads recorded in a processed item's run JSON. */

export interface S3OutputUploadInfo {
  /** Bucket the S3 Output node wrote to. */
  bucket: string
  /** Object key of the uploaded JSON file. */
  key: string
  /** ISO timestamp of the last manual re-sync, when one happened. */
  syncedAt: string | null
  /** Failure message from the last manual re-sync attempt, when it failed. */
  syncError: string | null
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

/** Node-output payloads with an ``s3_bucket`` + ``s3_key`` upload record. */
export function s3OutputUploadsFromItemOutput(
  output: Record<string, unknown> | null | undefined,
): S3OutputUploadInfo[] {
  if (!isPlainObject(output)) return []
  const uploads: S3OutputUploadInfo[] = []
  for (const payload of Object.values(output)) {
    if (!isPlainObject(payload)) continue
    const bucket = payload.s3_bucket
    const key = payload.s3_key
    if (typeof bucket !== 'string' || !bucket || typeof key !== 'string' || !key) continue
    if (!isPlainObject(payload.consolidated)) continue
    uploads.push({
      bucket,
      key,
      syncedAt: typeof payload.s3_synced_at === 'string' ? payload.s3_synced_at : null,
      syncError: typeof payload.s3_sync_error === 'string' ? payload.s3_sync_error : null,
    })
  }
  return uploads
}
