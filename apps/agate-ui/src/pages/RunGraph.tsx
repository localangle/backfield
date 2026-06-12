import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import ConfirmDialog from '@/components/ConfirmDialog'
import { FlowTitleRow } from '@/components/flow-builder/FlowTitleRow'
import { FlowDescriptionField } from '@/components/flow-builder/FlowDescriptionField'
import { PageBreadcrumbs } from '@/components/PageBreadcrumbs'
import { Button } from '@/components/ui/button'
import GuidedFlowBuilder, { type GuidedFlowBuilderHandle } from '@/pages/GuidedFlowBuilder'
import { createRun, deleteGraph, getGraph, getProject, getRun, updateGraph, type Graph, type Run } from '@/lib/api'
import { getInvalidFlowNodeIds, hydrateFromSpec } from '@/lib/flowGraphModel'
import {
  buildProjectBreadcrumbItems,
  useProjectAndWorkspace,
} from '@/lib/projectBreadcrumbs'
import { Edit, Loader2, Play, Save, Trash2 } from 'lucide-react'

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
  const [flowName, setFlowName] = useState('')
  const pollTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const { project: flowProject, workspace: flowWorkspace } = useProjectAndWorkspace(
    graph?.project_id,
  )

  const breadcrumbItems = useMemo(
    () =>
      buildProjectBreadcrumbItems({
        project: flowProject,
        workspace: flowWorkspace,
        tail: [{ label: (editMode ? flowName : graph?.name)?.trim() || 'Flow' }],
      }),
    [editMode, flowName, flowProject, flowWorkspace, graph?.name],
  )

  const graphInvalid = useMemo(() => {
    if (!graph) return false
    const hydrated = hydrateFromSpec(graph.spec)
    if (!hydrated.ok) return true
    return getInvalidFlowNodeIds(hydrated.model).size > 0
  }, [graph])

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
      setFlowName(data.name)
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
    if (graphId) void loadGraph(graphId)
    setEditMode(false)
  }, [graphId, loadGraph])

  const handleSaveGraph = useCallback(async () => {
    setSaving(true)
    try {
      if (graph) {
        builderRef.current?.setGraphDescription(graph.description ?? '')
        builderRef.current?.setGraphName(flowName)
      }
      const ok = (await builderRef.current?.save()) ?? false
      if (ok) {
        setEditMode(false)
        if (graphId) await loadGraph(graphId)
      }
    } finally {
      setSaving(false)
    }
  }, [flowName, graph, graphId, loadGraph])

  const executeRun = useCallback(async () => {
    if (!graphId) return

    try {
      setRunning(true)
      setShowRunPanel(true)
      const inputsReady = (await builderRef.current?.flushRunInputs()) ?? true
      if (!inputsReady) {
        setRunning(false)
        setShowRunPanel(false)
        showModal({
          title: 'Run failed',
          description:
            'Could not save the latest flow inputs before starting the run. Fix any issues and try again.',
          type: 'error',
          confirmText: 'OK',
          onConfirm: () => {},
        })
        return
      }
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

    if (graphInvalid) {
      showModal({
        title: 'Flow needs attention',
        description:
          'This flow has an invalid connection. Fix the highlighted step before running it.',
        type: 'warning',
        confirmText: 'OK',
        onConfirm: () => {},
      })
      return
    }

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
  }, [graphId, graphInvalid, executeRun, showModal])

  const handleFlowNameChange = useCallback((nextName: string) => {
    setFlowName(nextName)
    builderRef.current?.setGraphName(nextName)
  }, [])

  const handleFlowDescriptionSave = useCallback(
    async (nextDescription: string) => {
      if (!graph) return
      await updateGraph(graph.id, {
        name: graph.name,
        description: nextDescription,
        project_id: graph.project_id,
        spec: graph.spec,
      })
      await loadGraph(graph.id)
    },
    [graph, loadGraph],
  )

  const confirmDeleteFlow = useCallback(async () => {
    if (!graph) return

    try {
      const projectSlug = flowProject?.slug ?? (await getProject(graph.project_id)).slug
      await deleteGraph(graph.id)
      navigate(`/project/${encodeURIComponent(projectSlug)}`)
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
  }, [flowProject?.slug, graph, navigate, showModal])

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
            Back to workspaces
          </Button>
        </Link>
      </div>
    )
  }

  return (
    <div className="flex h-screen flex-col">
      <div className="sticky top-0 z-10 border-b bg-background">
        <div className="container mx-auto px-4 py-3">
          <PageBreadcrumbs items={breadcrumbItems} />
          <div className="mt-1.5 flex items-center justify-between gap-4">
            <div className="min-w-0 flex-1">
              <FlowTitleRow
                alwaysEditable={editMode}
                name={editMode ? flowName : (graph?.name ?? 'Flow')}
                onChange={editMode ? handleFlowNameChange : undefined}
                canEdit={editMode}
              />
            </div>
            <div className="flex shrink-0 items-center gap-2">
          {editMode ? (
            <>
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
            </>
          ) : (
            <>
              <Button
                onClick={handleRunFlow}
                disabled={running || graphInvalid}
                title={graphInvalid ? 'Fix invalid connections before running this flow.' : undefined}
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
            </>
          )}
            </div>
          </div>
          <FlowDescriptionField
            value={graph?.description ?? ''}
            onChange={(next) => {
              if (!graph) return
              setGraph({ ...graph, description: next })
              builderRef.current?.setGraphDescription(next)
            }}
            onBlurSave={editMode ? handleFlowDescriptionSave : undefined}
            canEdit={editMode}
            className="mt-1"
          />
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
