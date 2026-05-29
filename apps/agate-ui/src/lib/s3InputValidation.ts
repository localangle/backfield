const S3_URI_PREFIX = /^s3:\/\//i

/** Strip leading s3:// and surrounding whitespace from a bucket name field. */
export function normalizeS3BucketName(value: string): string {
  return value.trim().replace(S3_URI_PREFIX, '').trim()
}

/** Gate/save validation for the S3 bucket field; null when valid. */
export function s3BucketFieldError(value: string): string | null {
  if (normalizeS3BucketName(value) === '') {
    return 'Enter the S3 bucket name before continuing.'
  }
  return null
}

export function isValidS3BucketName(value: string): boolean {
  return s3BucketFieldError(value) === null
}

export const S3_DEFAULT_MAX_FILES = 500
export const S3_MAX_FILES_CAP = 10_000

export function clampS3MaxFiles(value: number): number {
  return Math.max(1, Math.min(value, S3_MAX_FILES_CAP))
}

/** Parse max-files text on blur; empty or invalid input falls back to the default. */
export function normalizeS3MaxFilesInput(value: string): number {
  const trimmed = value.trim()
  if (!trimmed) {
    return S3_DEFAULT_MAX_FILES
  }
  const parsed = parseInt(trimmed, 10)
  if (!Number.isFinite(parsed)) {
    return S3_DEFAULT_MAX_FILES
  }
  return clampS3MaxFiles(parsed)
}

/** Optional S3 prefix: trim, collapse trailing slashes to one, add trailing slash when non-empty. */
export function normalizeS3FolderPath(value: string): string {
  const trimmed = value.trim()
  if (!trimmed) {
    return ''
  }
  const withoutTrailing = trimmed.replace(/\/+$/, '')
  if (!withoutTrailing) {
    return ''
  }
  return `${withoutTrailing}/`
}
