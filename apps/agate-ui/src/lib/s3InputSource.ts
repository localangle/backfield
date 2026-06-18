import { normalizeS3BucketName, normalizeS3FolderPath } from '@/lib/s3InputValidation'

export interface S3InputSource {
  bucket: string
  folderPath: string
  uri: string
}

type GraphSpecLike = {
  nodes?: Array<{ type: string; params?: Record<string, unknown> }>
} | undefined

/** Resolve the configured S3 bucket and folder prefix from a saved flow spec. */
export function s3InputSourceFromGraphSpec(spec: GraphSpecLike): S3InputSource | null {
  const s3Node = spec?.nodes?.find((node) => node.type === 'S3Input')
  if (!s3Node) return null

  const params = s3Node.params ?? {}
  const bucket = normalizeS3BucketName(String(params.bucket ?? ''))
  if (!bucket) return null

  const folderPath = normalizeS3FolderPath(String(params.folder_path ?? ''))
  const uri = folderPath ? `s3://${bucket}/${folderPath}` : `s3://${bucket}/`
  return { bucket, folderPath, uri }
}
