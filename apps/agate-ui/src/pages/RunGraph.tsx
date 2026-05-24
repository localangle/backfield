import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import ConfirmDialog from '@/components/ConfirmDialog'
import { Button } from '@/components/ui/button'
import GuidedFlowBuilder, { type GuidedFlowBuilderHandle } from '@/pages/GuidedFlowBuilder'
import { createRun, deleteGraph, getGraph, getRun, updateGraph, type Graph, type Run } from '@/lib/api'
import { ArrowLeft, Edit, Loader2, Play, Save, Trash2 } from 'lucide-react'

export default function RunGraph() {
  const { graphId } = useParams<{ graphId: string }>()
  const navigate = useNavigate()
  const builderRef = useRef<GuidedFlowBuilderHandle>(null)

  const [graph, setGraph] = useState<Graph | null>(null)
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)
  const [currentRun, setCurrentRun] = useState<Run | null>(null)
  const [editMode, setEditMode] = useState(false)
  const [saving, setSaving] = useState(false)
  const [showRunPanel, setShowRunPanel] = useState(false)
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [editingTitle, setEditingTitle] = useState(false)
  const [titleValue, setTitleValue] = useState('')

  const pollTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const [modalOpen, setModalOpen] = useState(false)
  const [modalConfig, setModalConfig] = useState<{
    title: string
    description: string
    type: 'info' | 'warning' | 'error' | 'success'
    confirmText?: string
    cancelText?: string
    onConfirm: () => void
    onCancel?: () => void
  } | null>(null)

  const showModal = useCallback((config: typeof modalConfig) => {
    setModalConfig(config)
    setModalOpen(true)
  }, [])

  const loadGraph = useCallback(async (id: string) => {
    try {
      setLoading(true)
      const data = await getGraph(id)
      setGraph(data)
      setTitleValue(data.name)
    } catch (error) {
      console.error('Failed to load graph:', error)
      setGraph(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!graphId) return
    void loadGraph(graphId)
    return () => {
      if (pollTimeoutRef.current) {
        clearTimeout(pollTimeoutRef.current)
        pollTimeoutRef.current = null
      }
    }
  }, [graphId, loadGraph])

  const handleGraphLoaded = useCallback(
    (payload: { id: string; name: string; projectId: number }) => {
      setGraph((current) =>
        current
          ? { ...current, id: payload.id, name: payload.name, project_id: payload.projectId }
          : ({
              id: payload.id,
              name: payload.name,
              project_id: payload.projectId,
            } as Graph),
      )
      setTitleValue(payload.name)
      setLoading(false)
    },
    [],
  )

  const handleEnterEdit = useCallback(() => {
    builderRef.current?.takeSnapshot()
    setEditMode(true)
  }, [])

  const handleCancelEdit = useCallback(() => {
    builderRef.current?.restoreSnapshot()
    setEditMode(false)
  }, [])

  const handleSaveGraph = useCallback(async () => {
    setSaving(true)
    try {
      const ok = (await builderRef.current?.save()) ?? false
      if (ok) {
        setEditMode(false)
        if (graphId) await loadGraph(graphId)
      }
    } finally {
      setSaving(false)
    }
  }, [graphId, loadGraph])

  const executeRun = useCallback(async () => {
    if (!graphId) return

    try {
      setRunning(true)
      setShowRunPanel(true)
      const run = await createRun(graphId, { input: {} })
      setCurrentRun(run)

      const pollRunStatus = async () => {
        try {
          return await getRun(run.id)
        } catch (error) {
          console.error('Failed to poll run status:', error)
          return null
        }
      }

      const checkDone = (updated: Run | null) =>
        updated?.status === 'completed' || updated?.status === 'completed_with_errors'

      pollTimeoutRef.current = window.setTimeout(async () => {
        pollTimeoutRef.current = null
        const updated = await pollRunStatus()
        if (updated) setCurrentRun(updated)
        if (checkDone(updated)) {
          window.clearInterval(interval)
          setRunning(false)
        }
      }, 1000)

      const interval = window.setInterval(async () => {
        const updated = await pollRunStatus()
        if (updated) setCurrentRun(updated)
        if (checkDone(updated)) {
          window.clearInterval(interval)
          if (pollTimeoutRef.current) {
            window.clearTimeout(pollTimeoutRef.current)
            pollTimeoutRef.current = null
          }
          setRunning(false)
        }
      }, 2000)
    } catch (error) {
      console.error('Failed to create run:', error)
      showModal({
        title: 'Run failed',
        description: 'Failed to create run. Please check the console for details and try again.',
        type: 'error',
        confirmText: 'OK',
        onConfirm: () => {},
      })
      setRunning(false)
      setShowRunPanel(false)
    }
  }, [graphId, showModal])

  const handleRunFlow = useCallback(() => {
    if (!graphId) return

    if (builderRef.current?.hasNodeType('APIInput')) {
      showModal({
        title: 'API input flow',
        description:
          'This flow uses an API input and is designed to be triggered via API calls. Manual runs may be limited.',
        type: 'warning',
        confirmText: 'Continue anyway',
        onConfirm: () => {
          void executeRun()
        },
      })
      return
    }

    void executeRun()
  }, [graphId, executeRun, showModal])

  const handleTitleClick = useCallback(() => {
    setEditingTitle(true)
  }, [])

  const handleTitleSave = useCallback(async () => {
    if (!graph || !titleValue.trim()) {
      setEditingTitle(false)
      setTitleValue(graph?.name ?? '')
      return
    }

    try {
      await updateGraph(graph.id, {
        name: titleValue,
        project_id: graph.project_id,
        spec: {
          ...graph.spec,
          name: titleValue.toLowerCase().replace(/\s+/g, '_'),
        },
      })
      await loadGraph(graph.id)
      setEditingTitle(false)
    } catch (error) {
      console.error('Failed to update title:', error)
      setEditingTitle(false)
      setTitleValue(graph.name)
    }
  }, [graph, titleValue, loadGraph])

  const handleTitleKeyDown = useCallback(
    (event: React.KeyboardEvent) => {
      if (event.key === 'Enter') {
        void handleTitleSave()
      } else if (event.key === 'Escape') {
        setEditingTitle(false)
        setTitleValue(graph?.name ?? '')
      }
    },
    [handleTitleSave, graph?.name],
  )

  const confirmDeleteFlow = useCallback(async () => {
    if (!graph) return

    try {
      await deleteGraph(graph.id)
      navigate('/')
    } catch (error) {
      console.error('Failed to delete flow:', error)
      showModal({
        title: 'Delete failed',
        description: 'Failed to delete flow. Please check the console for details and try again.',
        type: 'error',
        confirmText: 'OK',
        onConfirm: () => {},
      })
    } finally {
      setDeleteDialogOpen(false)
    }
  }, [graph, navigate, showModal])

  if (loading && !graph) {
    return (
      <div className="flex h-screen flex-col items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (!graph && !loading) {
    return (
      <div className="py-12 text-center">
        <p className="text-muted-foreground">Flow not found</p>
        <Link to="/">
          <Button variant="link" className="mt-4">
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back to flows
          </Button>
        </Link>
      </div>
    )
  }

  return (
    <div className="flex h-screen flex-col">
      <div className="sticky top-0 z-10 border-b bg-background">
        <div className="container mx-auto flex items-center justify-between px-4 py-4">
          <div className="flex items-center gap-4">
            <Link to="/">
              <Button variant="ghost" size="sm">
                <ArrowLeft className="mr-2 h-4 w-4" />
                Back
              </Button>
            </Link>
            <div>
              {editingTitle ? (
                <input
                  type="text"
                  value={titleValue}
                  onChange={(event) => setTitleValue(event.target.value)}
                  onBlur={() => void handleTitleSave()}
                  onKeyDown={handleTitleKeyDown}
                  autoFocus
                  className="border-b-2 border-primary bg-transparent px-1 text-2xl font-bold outline-none"
                />
              ) : (
                <h1
                  className="cursor-pointer text-2xl font-bold transition-colors hover:text-primary"
                  onClick={handleTitleClick}
                  title="Click to edit title"
                >
                  {graph?.name ?? 'Flow'}
                </h1>
              )}
              <p className="text-sm text-muted-foreground">
                {editMode
                  ? 'Edit mode — add steps, change bookends, or save your changes'
                  : 'Click any step to view details and run this flow'}
              </p>
            </div>
          </div>

          {editMode ? (
            <div className="flex gap-2">
              <Button variant="outline" onClick={handleCancelEdit}>
                Cancel
              </Button>
              <Button onClick={() => void handleSaveGraph()} disabled={saving}>
                <Save className="mr-2 h-4 w-4" />
                {saving ? 'Saving…' : 'Save changes'}
              </Button>
              <Button variant="destructive" className="text-white" onClick={() => setDeleteDialogOpen(true)}>
                <Trash2 className="mr-2 h-4 w-4" />
                Delete flow
              </Button>
            </div>
          ) : (
            <div className="flex gap-2">
              <Button
                onClick={handleRunFlow}
                disabled={running}
                className="bg-black text-white hover:bg-gray-800"
              >
                {running ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Running…
                  </>
                ) : (
                  <>
                    <Play className="mr-2 h-4 w-4" />
                    Run flow
                  </>
                )}
              </Button>
              <Button variant="outline" onClick={handleEnterEdit}>
                <Edit className="mr-2 h-4 w-4" />
                Edit flow
              </Button>
              <Button variant="destructive" className="text-white" onClick={() => setDeleteDialogOpen(true)}>
                <Trash2 className="mr-2 h-4 w-4" />
                Delete flow
              </Button>
            </div>
          )}
        </div>
      </div>

      <GuidedFlowBuilder
        ref={builderRef}
        variant="run"
        readOnly={!editMode}
        hideHeader
        running={running}
        currentRun={currentRun}
        showRunPanel={showRunPanel}
        onCloseRunPanel={() => setShowRunPanel(false)}
        onGraphLoaded={handleGraphLoaded}
        onSaved={() => {
          setEditMode(false)
          if (graphId) void loadGraph(graphId)
        }}
        className="min-h-0 flex-1"
      />

      {modalConfig && (
        <ConfirmDialog
          open={modalOpen}
          onOpenChange={setModalOpen}
          title={modalConfig.title}
          description={modalConfig.description}
          type={modalConfig.type}
          confirmText={modalConfig.confirmText}
          cancelText={modalConfig.cancelText}
          onConfirm={modalConfig.onConfirm}
          onCancel={modalConfig.onCancel}
        />
      )}

      <ConfirmDialog
        open={deleteDialogOpen}
        onOpenChange={setDeleteDialogOpen}
        title="Delete flow"
        description={`Are you sure you want to delete "${graph?.name}"? This action cannot be undone and will also delete all associated runs.`}
        type="warning"
        confirmText="Delete"
        cancelText="Cancel"
        onConfirm={() => void confirmDeleteFlow()}
        onCancel={() => setDeleteDialogOpen(false)}
      />
    </div>
  )
}
