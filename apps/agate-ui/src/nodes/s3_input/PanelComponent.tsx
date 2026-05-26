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

import { useEffect, useState } from 'react'
import { NodePanelTabGate } from '@/components/node-panel/NodePanelTabContext'
import { NodePanelOutputsSection } from '@/components/node-panel/NodePanelOutputsSection'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { getNodeOutputById, type NodeOutputLookupSpec } from '@/lib/nodeOutputs'

const MAX_FILES_MIN = 1
const MAX_FILES_MAX = 10000
const MAX_FILES_DEFAULT = 500

function clampMaxFiles(value: number): number {
  if (!Number.isFinite(value)) return MAX_FILES_DEFAULT
  return Math.min(MAX_FILES_MAX, Math.max(MAX_FILES_MIN, Math.trunc(value)))
}

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
  const storedMaxFiles = clampMaxFiles(Number(node.data.max_files ?? MAX_FILES_DEFAULT))
  const [maxFilesDraft, setMaxFilesDraft] = useState(String(storedMaxFiles))

  useEffect(() => {
    setMaxFilesDraft(String(clampMaxFiles(Number(node.data.max_files ?? MAX_FILES_DEFAULT))))
  }, [node.id, node.data.max_files])

  const commitMaxFiles = () => {
    if (!setNodes) return
    const digits = maxFilesDraft.replace(/\D/g, '')
    const parsed = digits === '' ? MAX_FILES_DEFAULT : parseInt(digits, 10)
    const next = clampMaxFiles(parsed)
    setMaxFilesDraft(String(next))
    setNodes((nds: any[]) =>
      nds.map((n: any) =>
        n.id === node.id ? { ...n, data: { ...n.data, max_files: next } } : n,
      ),
    )
  }

  const rawOutputs = currentRun?.node_outputs as Record<string, unknown> | undefined
  const slice = rawOutputs
    ? (getNodeOutputById(rawOutputs, node.id, nodeOutputLookupSpec ?? undefined) as
        | Record<string, unknown>
        | undefined)
    : undefined

  return (
    <>
      <NodePanelTabGate tab="settings">
        <div className="space-y-3">
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
                      n.id === node.id ? { ...n, data: { ...n.data, bucket: e.target.value } } : n,
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
              Optional prefix inside the bucket (for example{' '}
              <span className="font-mono">input/</span>).
            </p>
          </div>

          <div>
            <Label htmlFor="max-files" className="text-xs text-muted-foreground">
              Max files per run
            </Label>
            {editMode && setNodes ? (
              <Input
                id="max-files"
                type="text"
                inputMode="numeric"
                autoComplete="off"
                value={maxFilesDraft}
                onChange={(e) => setMaxFilesDraft(e.target.value.replace(/\D/g, ''))}
                onBlur={commitMaxFiles}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    commitMaxFiles()
                  }
                }}
                className="mt-1 text-xs [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
              />
            ) : (
              <div className="mt-1 p-2 bg-muted rounded">
                <span className="text-xs">{storedMaxFiles}</span>
              </div>
            )}
          </div>
        </div>
      </NodePanelTabGate>

      <NodePanelTabGate tab="outputs">
        {slice && typeof slice.total_files === 'number' ? (
          <NodePanelOutputsSection>
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
          </NodePanelOutputsSection>
        ) : null}
      </NodePanelTabGate>
    </>
  )
}
