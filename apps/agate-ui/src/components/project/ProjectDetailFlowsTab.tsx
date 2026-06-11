import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  listGraphs,
  deleteGraph,
  createGraph,
  type Graph,
  type GraphCreate,
} from '@/lib/api'
import { flowDescriptionTableText } from '@/components/flow-builder/FlowDescriptionField'
import { formatDate } from '@/lib/utils'
import { Loader2, Copy, Trash2 } from 'lucide-react'

interface ProjectDetailFlowsTabProps {
  projectId: number
  projectSlug: string
  onDataChanged?: () => void
}

export default function ProjectDetailFlowsTab({
  projectId,
  projectSlug,
  onDataChanged,
}: ProjectDetailFlowsTabProps) {
  const [graphs, setGraphs] = useState<Graph[]>([])
  const [loading, setLoading] = useState(true)
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [flowToDelete, setFlowToDelete] = useState<Graph | null>(null)
  const navigate = useNavigate()

  const loadData = useCallback(async () => {
    try {
      setLoading(true)
      const graphsData = await listGraphs()
      setGraphs(graphsData.filter((g) => g.project_id === projectId))
    } catch (error) {
      console.error('Failed to load flows:', error)
    } finally {
      setLoading(false)
    }
  }, [projectId])

  useEffect(() => {
    void loadData()
  }, [loadData])

  const handleDeleteFlow = (flow: Graph) => {
    setFlowToDelete(flow)
    setDeleteDialogOpen(true)
  }

  const handleDuplicateFlow = async (flow: Graph) => {
    try {
      const duplicateData: GraphCreate = {
        name: `Copy of ${flow.name}`,
        description: flow.description ?? '',
        project_id: flow.project_id,
        spec: flow.spec,
      }
      const newGraph = await createGraph(duplicateData)
      setGraphs((prev) => [...prev, newGraph])
      navigate(`/flow/${newGraph.id}/edit`)
      onDataChanged?.()
    } catch (error) {
      console.error('Failed to duplicate flow:', error)
    }
  }

  const confirmDeleteFlow = async () => {
    if (!flowToDelete) return
    try {
      await deleteGraph(flowToDelete.id)
      setGraphs((prev) => prev.filter((g) => g.id !== flowToDelete.id))
      setDeleteDialogOpen(false)
      setFlowToDelete(null)
      onDataChanged?.()
    } catch (error) {
      console.error('Failed to delete flow:', error)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <>
      <p className="text-sm text-muted-foreground mb-4">
        Flows in this project. Open a flow to view or run it.
      </p>

      {graphs.length === 0 ? (
        <Card>
          <CardContent className="py-12">
            <p className="text-center text-muted-foreground">
              No flows in this project yet. Create one to get started.
            </p>
          </CardContent>
        </Card>
      ) : (
        <Card className="overflow-hidden">
          <CardContent className="p-0">
            <div className="w-full overflow-x-auto">
              <table className="w-full min-w-[640px] text-sm">
                <thead className="border-b bg-muted/50">
                  <tr>
                    <th className="text-left p-3 sm:p-4 font-medium">Name</th>
                    <th className="text-left p-3 sm:p-4 font-medium hidden md:table-cell">Description</th>
                    <th className="text-left p-3 sm:p-4 font-medium hidden sm:table-cell">Created</th>
                    <th className="text-right p-3 sm:p-4 font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {graphs.map((graph) => (
                    <tr
                      key={graph.id}
                      className="border-b last:border-b-0 hover:bg-muted/[0.07] transition-colors"
                    >
                      <td
                        className="p-3 sm:p-4 cursor-pointer align-top"
                        onClick={() => navigate(`/flow/${graph.id}`)}
                      >
                        <div className="font-medium">{graph.name}</div>
                      </td>
                      <td
                        className="p-3 sm:p-4 text-sm text-muted-foreground cursor-pointer align-top hidden md:table-cell"
                        onClick={() => navigate(`/flow/${graph.id}`)}
                      >
                        <div className="line-clamp-2 max-w-md">
                          {flowDescriptionTableText(graph.description)}
                        </div>
                      </td>
                      <td
                        className="p-3 sm:p-4 text-muted-foreground cursor-pointer align-top hidden sm:table-cell whitespace-nowrap"
                        onClick={() => navigate(`/flow/${graph.id}`)}
                      >
                        {formatDate(graph.created_at, { includeTime: false })}
                      </td>
                      <td className="p-3 sm:p-4 align-top">
                        <div className="flex items-center justify-end gap-1">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={(e) => {
                              e.stopPropagation()
                              handleDuplicateFlow(graph)
                            }}
                            className="h-8 w-8 p-0 text-muted-foreground hover:text-foreground"
                            title="Duplicate flow"
                          >
                            <Copy className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={(e) => {
                              e.stopPropagation()
                              handleDeleteFlow(graph)
                            }}
                            className="h-8 w-8 p-0 text-muted-foreground hover:text-destructive"
                            title="Delete flow"
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      <Dialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete flow</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete &quot;{flowToDelete?.name}&quot;? This cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteDialogOpen(false)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={confirmDeleteFlow}>
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
