import { useEffect, useState } from 'react'
import { NodePanelTabGate } from '@/components/node-panel/NodePanelTabContext'
import IngressApiRunsSection from '@/components/node-panel/IngressApiRunsSection'
import type { GraphPanelContext } from '@/components/NodePanel'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import {
  JSON_INPUT_MAX_DOCUMENTS,
  JSON_INPUT_SOURCE_FILE_KEY,
  buildJsonInputNodeData,
  getJsonInputDocumentList,
  isJsonInputMultiDocument,
  markJsonInputNodeDataInvalid,
  mergeJsonInputUploads,
  parseJsonInputEditorText,
  parseJsonInputFileText,
  type JsonInputDocument,
} from '@/lib/jsonInputValidation'
import { getNodeOutputById, type NodeOutputLookupSpec } from '@/lib/nodeOutputs'
import JsonFileDropZone from './JsonFileDropZone'
import { JSON_INPUT_SCHEMA_EXAMPLE } from './schemaExample'

interface JSONInputPanelProps {
  node: any
  currentRun?: any
  editMode?: boolean
  setNodes?: (nodes: any) => void
  graphContext?: GraphPanelContext
  nodeOutputLookupSpec?: NodeOutputLookupSpec | null
}

function editorTextForDocument(doc: JsonInputDocument): string {
  const fields = { ...doc }
  delete fields[JSON_INPUT_SOURCE_FILE_KEY]
  return JSON.stringify(fields, null, 2)
}

export default function JSONInputPanel({
  node,
  currentRun,
  editMode,
  setNodes,
  graphContext,
  nodeOutputLookupSpec,
}: JSONInputPanelProps) {
  const [jsonText, setJsonText] = useState('')
  const [jsonError, setJsonError] = useState('')
  const [uploadError, setUploadError] = useState('')
  const [selectedIndex, setSelectedIndex] = useState(0)

  const nodeData = (node.data || {}) as Record<string, unknown>
  const documents = getJsonInputDocumentList(nodeData)
  const multi = isJsonInputMultiDocument(nodeData)
  const safeIndex = Math.min(selectedIndex, Math.max(0, documents.length - 1))

  useEffect(() => {
    setSelectedIndex(0)
    try {
      const docs = getJsonInputDocumentList((node.data || {}) as Record<string, unknown>)
      setJsonText(editorTextForDocument(docs[0] ?? { text: '' }))
      setJsonError('')
      setUploadError('')
    } catch {
      setJsonText('{\n  "text": ""\n}')
    }
  }, [node.id])

  const patchNodeData = (next: Record<string, unknown>) => {
    if (!setNodes) return
    setNodes((nds: any[]) =>
      nds.map((n: any) => (n.id === node.id ? { ...n, data: next } : n)),
    )
  }

  const handleJsonChange = (value: string) => {
    setJsonText(value)

    const result = parseJsonInputEditorText(value)
    if (!result.ok) {
      setJsonError(result.error)
      if (setNodes) {
        setNodes((nds: any[]) =>
          nds.map((n: any) =>
            n.id === node.id
              ? { ...n, data: markJsonInputNodeDataInvalid(n.data as Record<string, unknown>) }
              : n,
          ),
        )
      }
      return
    }

    setJsonError('')
    const currentDocs = getJsonInputDocumentList(nodeData)
    const index = Math.min(selectedIndex, Math.max(0, currentDocs.length - 1))
    const previous = currentDocs[index]
    const sourceName =
      typeof previous?.[JSON_INPUT_SOURCE_FILE_KEY] === 'string'
        ? String(previous[JSON_INPUT_SOURCE_FILE_KEY])
        : undefined
    const updated: JsonInputDocument = {
      ...result.data,
      text: result.data.text,
      ...(sourceName ? { [JSON_INPUT_SOURCE_FILE_KEY]: sourceName } : {}),
    }
    const nextDocs = currentDocs.map((doc, i) => (i === index ? updated : doc))
    patchNodeData(buildJsonInputNodeData(nextDocs, nodeData))
  }

  const handleFiles = async (files: File[]) => {
    setUploadError('')
    const uploads: JsonInputDocument[] = []
    for (const file of files) {
      const raw = await file.text()
      const parsed = parseJsonInputFileText(raw, file.name)
      if (!parsed.ok) {
        setUploadError(parsed.error)
        return
      }
      uploads.push(parsed.document)
    }
    const merged = mergeJsonInputUploads(nodeData, uploads)
    if (!merged.ok) {
      setUploadError(merged.error)
      return
    }
    const nextDocs = getJsonInputDocumentList(merged.data)
    const nextIndex = Math.max(0, nextDocs.length - uploads.length)
    setSelectedIndex(nextIndex)
    setJsonText(editorTextForDocument(nextDocs[nextIndex] ?? { text: '' }))
    setJsonError('')
    patchNodeData(merged.data)
  }

  const removeDocumentAt = (index: number) => {
    const nextDocs = documents.filter((_, i) => i !== index)
    const nextData = buildJsonInputNodeData(nextDocs, nodeData)
    let nextIndex = selectedIndex
    if (nextDocs.length === 0) nextIndex = 0
    else if (selectedIndex > index) nextIndex = selectedIndex - 1
    else if (selectedIndex >= nextDocs.length) nextIndex = nextDocs.length - 1
    setSelectedIndex(nextIndex)
    setJsonText(editorTextForDocument(nextDocs[nextIndex] ?? { text: '' }))
    setJsonError('')
    patchNodeData(nextData)
  }

  const selectDocument = (index: number) => {
    setSelectedIndex(index)
    setJsonText(editorTextForDocument(documents[index] ?? { text: '' }))
    setJsonError('')
  }

  const isDisabled = !(editMode && setNodes)

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
          <JsonFileDropZone disabled={isDisabled} onFiles={handleFiles} />
          {uploadError ? <p className="text-xs text-red-500">{uploadError}</p> : null}

          {multi ? (
            <div className="space-y-1">
              <Label>
                Files ({documents.length} of {JSON_INPUT_MAX_DOCUMENTS})
              </Label>
              <ul className="max-h-40 space-y-1 overflow-y-auto rounded-md border p-1">
                {documents.map((doc, index) => {
                  const name =
                    typeof doc[JSON_INPUT_SOURCE_FILE_KEY] === 'string'
                      ? String(doc[JSON_INPUT_SOURCE_FILE_KEY])
                      : `File ${index + 1}`
                  const selected = index === safeIndex
                  return (
                    <li key={`${name}-${index}`} className="flex items-center gap-1">
                      <button
                        type="button"
                        className={
                          selected
                            ? 'flex-1 truncate rounded px-2 py-1 text-left text-xs bg-accent'
                            : 'flex-1 truncate rounded px-2 py-1 text-left text-xs hover:bg-muted'
                        }
                        disabled={isDisabled}
                        onClick={() => selectDocument(index)}
                      >
                        {name}
                      </button>
                      <button
                        type="button"
                        className="shrink-0 rounded px-2 py-1 text-xs text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-50"
                        disabled={isDisabled}
                        onClick={() => removeDocumentAt(index)}
                        aria-label={`Remove ${name}`}
                      >
                        Remove
                      </button>
                    </li>
                  )
                })}
              </ul>
            </div>
          ) : null}

          <div className="space-y-2">
            <Label htmlFor="node-json">{multi ? 'Selected file content' : 'Content'}</Label>
            <Textarea
              id="node-json"
              value={jsonText}
              onChange={(e) => handleJsonChange(e.target.value)}
              placeholder={`{\n  "text": "Your text here...",\n  "headline": "Optional headline"\n}`}
              className="min-h-[300px] mt-1 font-mono text-xs"
              disabled={isDisabled}
            />
            {jsonError && <p className="text-xs text-red-500 mt-1">{jsonError}</p>}
          </div>
        </div>

        <IngressApiRunsSection
          node={node}
          editMode={editMode}
          setNodes={setNodes}
          publicRunEnabled={Boolean(graphContext?.publicRunEnabled)}
          onPublicRunEnabledChange={graphContext?.onPublicRunEnabledChange}
        />
      </NodePanelTabGate>

      <NodePanelTabGate tab="info">
        <div className="space-y-2">
          <p className="text-sm text-muted-foreground leading-relaxed">
            Paste content or upload one or more JSON files (up to {JSON_INPUT_MAX_DOCUMENTS}).
            Each file becomes its own item when you run the flow. Include a text field in each
            object (it may be empty); other fields are optional and can be referenced in prompts
            (for example {'{headline}'}).
          </p>
          <Label htmlFor="node-json-schema">Example shape</Label>
          <Textarea
            id="node-json-schema"
            readOnly
            value={JSON_INPUT_SCHEMA_EXAMPLE}
            className="min-h-[300px] mt-1 font-mono text-xs bg-muted/40 cursor-default"
            tabIndex={-1}
            aria-readonly
          />
        </div>
      </NodePanelTabGate>

      <NodePanelTabGate tab="outputs">
        {slice && typeof slice.text === 'string' ? (
          <div className="space-y-2">
            <div className="text-xs text-muted-foreground">
              Fields in output: {Object.keys(slice).length}
            </div>
            <div>
              <Label>Output preview</Label>
              <div className="text-xs font-mono p-2 bg-muted rounded mt-1 max-h-48 overflow-y-auto">
                {JSON.stringify(slice, null, 2)}
              </div>
            </div>
          </div>
        ) : null}
      </NodePanelTabGate>
    </>
  )
}
