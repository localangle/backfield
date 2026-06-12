import { FieldLabel } from '@/components/node-panel/FieldLabel'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { normalizeS3BucketName, normalizeS3FolderPath } from '@/lib/s3InputValidation'
import { getNodeOutputById, type NodeOutputLookupSpec } from '@/lib/nodeOutputs'

interface S3OutputPanelProps {
  node: any
  currentRun?: any
  editMode?: boolean
  setNodes?: (nodes: any) => void
  nodeOutputLookupSpec?: NodeOutputLookupSpec | null
}

export default function S3OutputPanel({
  node,
  currentRun,
  editMode,
  setNodes,
  nodeOutputLookupSpec,
}: S3OutputPanelProps) {
  const rawOutputs = currentRun?.node_outputs as Record<string, unknown> | undefined
  const slice = rawOutputs
    ? (getNodeOutputById(rawOutputs, node.id, nodeOutputLookupSpec ?? undefined) as
        | Record<string, unknown>
        | undefined)
    : undefined

  const bucketValue = String(node.data.bucket ?? '')

  const patchField = (field: string, value: unknown) => {
    if (!setNodes) return
    setNodes((nds: any[]) =>
      nds.map((n: any) => (n.id === node.id ? { ...n, data: { ...n.data, [field]: value } } : n)),
    )
  }

  return (
    <>
      <div className="space-y-3">
        <div>
          <FieldLabel htmlFor="bucket" required>
            S3 bucket name
          </FieldLabel>
          {editMode && setNodes ? (
            <Input
              id="bucket"
              value={node.data.bucket || ''}
              onChange={(e) => patchField('bucket', e.target.value)}
              onBlur={() => patchField('bucket', normalizeS3BucketName(String(node.data.bucket ?? '')))}
              placeholder="my-bucket-name"
              className="mt-1 text-xs font-mono"
              required
              aria-required
            />
          ) : (
            <div className="mt-1 p-2 bg-muted rounded">
              <span className="text-xs font-mono">
                {normalizeS3BucketName(bucketValue) || 'Not configured'}
              </span>
            </div>
          )}
          <p className="text-xs text-muted-foreground mt-1">
            The name of a S3 bucket your credentials can access. A leading{' '}
            <span className="font-mono">s3://</span> is removed automatically.
          </p>
        </div>

        <div>
          <Label htmlFor="output-path">Folder path</Label>
          {editMode && setNodes ? (
            <Input
              id="output-path"
              value={node.data.output_path || ''}
              onChange={(e) => patchField('output_path', e.target.value)}
              onBlur={() =>
                patchField('output_path', normalizeS3FolderPath(String(node.data.output_path ?? '')))
              }
              placeholder="output/results/"
              className="mt-1 text-xs font-mono"
            />
          ) : (
            <div className="mt-1 p-2 bg-muted rounded">
              <span className="text-xs font-mono">
                {normalizeS3FolderPath(String(node.data.output_path ?? '')) || '(root)'}
              </span>
            </div>
          )}
          <p className="text-xs text-muted-foreground mt-1">
            Optional prefix inside the bucket where result files are written (for example{' '}
            <span className="font-mono">output/</span>). Files are grouped into dated folders
            automatically.
          </p>
        </div>

        <div className="flex items-center justify-between gap-3">
          <div>
            <Label htmlFor="public-read">Public files</Label>
            <p className="text-xs text-muted-foreground mt-0.5">
              Make uploaded files publicly readable.
            </p>
          </div>
          {editMode && setNodes ? (
            <Switch
              id="public-read"
              checked={Boolean(node.data.public_read)}
              onCheckedChange={(checked) => patchField('public_read', checked)}
            />
          ) : (
            <div className="p-2 bg-muted rounded">
              <span className="text-xs">{node.data.public_read ? 'Yes' : 'No'}</span>
            </div>
          )}
        </div>
      </div>

      {slice && typeof slice.s3_key === 'string' && typeof slice.s3_bucket === 'string' && (
        <div className="pt-4 border-t mt-4">
          <Label className="text-sm font-medium">Latest run</Label>
          <div className="mt-2 space-y-2">
            <div className="text-xs space-y-1">
              <div className="flex justify-between items-start gap-2 p-2 bg-muted rounded">
                <span className="text-muted-foreground shrink-0">Saved to</span>
                <span className="font-mono text-[10px] break-all text-right">
                  s3://{String(slice.s3_bucket)}/{String(slice.s3_key)}
                </span>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
