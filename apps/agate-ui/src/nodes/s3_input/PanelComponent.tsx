// Auto-injected metadata for S3Input
const nodeMetadata = {
  "type": "S3Input",
  "label": "S3 Input",
  "icon": "Database",
  "color": "bg-blue-500",
  "description": "Load article text from JSON files in S3.",
  "category": "input",
  "inputs": [],
  "outputs": [
    {
      "id": "text",
      "label": "Text",
      "type": "string"
    }
  ],
  "defaultParams": {
    "bucket": "",
    "folder_path": "",
    "max_files": 500
  }
};

import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { getNodeOutputById, type NodeOutputLookupSpec } from '@/lib/nodeOutputs'

interface S3InputPanelProps {
  node: any
  onChange?: (text: string) => void
  onRun?: () => void
  running?: boolean
  currentRun?: any
  editMode?: boolean
  setNodes?: (nodes: any) => void
  nodeOutputLookupSpec?: NodeOutputLookupSpec | null
}

export default function S3InputPanel({
  node,
  currentRun,
  editMode,
  setNodes,
  nodeOutputLookupSpec,
}: S3InputPanelProps) {
  const rawOutputs = currentRun?.node_outputs as Record<string, unknown> | undefined
  const slice = rawOutputs
    ? (getNodeOutputById(rawOutputs, node.id, nodeOutputLookupSpec ?? undefined) as
        | Record<string, unknown>
        | undefined)
    : undefined
  return (
    <>
      <div className="space-y-3">
        <div>
          <Label className="text-sm font-medium">Description</Label>
          <p className="text-sm text-muted-foreground mt-1">
            Load article text from JSON files in S3.
          </p>
        </div>
      </div>

      <div className="pt-4 border-t">
        <div>
          <Label className="text-sm font-medium">Parameters</Label>
        </div>

        <div className="space-y-3 mt-2">
          <div>
            <Label htmlFor="bucket" className="text-xs text-muted-foreground">
              S3 bucket name
            </Label>
            {editMode && setNodes ? (
              <Input
                id="bucket"
                value={node.data.bucket || ''}
                onChange={(e) => {
                  setNodes((nds: any[]) =>
                    nds.map((n: any) =>
                      n.id === node.id
                        ? { ...n, data: { ...n.data, bucket: e.target.value } }
                        : n,
                    ),
                  )
                }}
                placeholder="my-bucket-name"
                className="mt-1 text-xs font-mono"
              />
            ) : (
              <div className="mt-1 p-2 bg-muted rounded">
                <span className="text-xs font-mono">{node.data.bucket || 'Not configured'}</span>
              </div>
            )}
          </div>

          <div>
            <Label htmlFor="folder-path" className="text-xs text-muted-foreground">
              Folder path (optional)
            </Label>
            {editMode && setNodes ? (
              <Input
                id="folder-path"
                value={node.data.folder_path || ''}
                onChange={(e) => {
                  setNodes((nds: any[]) =>
                    nds.map((n: any) =>
                      n.id === node.id
                        ? { ...n, data: { ...n.data, folder_path: e.target.value } }
                        : n,
                    ),
                  )
                }}
                placeholder="input/articles/"
                className="mt-1 text-xs font-mono"
              />
            ) : (
              <div className="mt-1 p-2 bg-muted rounded">
                <span className="text-xs font-mono">{node.data.folder_path || '(root)'}</span>
              </div>
            )}
            <p className="text-xs text-muted-foreground mt-1">
              Optional prefix inside the bucket (for example <span className="font-mono">input/</span>
              ).
            </p>
          </div>

          <div>
            <Label htmlFor="max-files" className="text-xs text-muted-foreground">
              Max files per run
            </Label>
            {editMode && setNodes ? (
              <Input
                id="max-files"
                type="number"
                min={1}
                max={10000}
                value={node.data.max_files ?? 500}
                onChange={(e) => {
                  const v = parseInt(e.target.value, 10)
                  const next = Number.isFinite(v) ? v : 500
                  setNodes((nds: any[]) =>
                    nds.map((n: any) =>
                      n.id === node.id ? { ...n, data: { ...n.data, max_files: next } } : n,
                    ),
                  )
                }}
                className="mt-1 text-xs"
              />
            ) : (
              <div className="mt-1 p-2 bg-muted rounded">
                <span className="text-xs">{node.data.max_files ?? 500}</span>
              </div>
            )}
          </div>
        </div>
      </div>

      {slice && typeof slice.total_files === 'number' && (
        <div className="pt-4 border-t">
          <Label className="text-sm font-medium">Latest run</Label>
          <div className="mt-2 space-y-2">
            <div className="text-xs space-y-1">
              <div className="flex justify-between items-center p-2 bg-muted rounded">
                <span className="text-muted-foreground">Total files</span>
                <span className="font-medium">{slice.total_files}</span>
              </div>
              <div className="flex justify-between items-center p-2 bg-green-50 rounded">
                <span className="text-muted-foreground">Valid text files</span>
                <span className="font-medium text-green-700">{slice.processed_files}</span>
              </div>
              {typeof slice.skipped_files === 'number' && slice.skipped_files > 0 && (
                <div className="flex justify-between items-center p-2 bg-yellow-50 rounded">
                  <span className="text-muted-foreground">Skipped</span>
                  <span className="font-medium text-yellow-700">{slice.skipped_files}</span>
                </div>
              )}
              {slice.source_file && (
                <div className="flex justify-between items-start gap-2 p-2 bg-muted rounded">
                  <span className="text-muted-foreground shrink-0">Source</span>
                  <span className="font-mono text-[10px] break-all text-right">
                    {String(slice.source_file)}
                  </span>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  )
}
