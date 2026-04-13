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
  listProjects,
  listGraphs,
  deleteGraph,
  updateGraph,
  createGraph,
  type Project,
  type Graph,
  type GraphCreate,
} from '@/lib/api'
import { formatDateCentral } from '@/lib/utils'
import { Loader2, Copy, Trash2, Plus } from 'lucide-react'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

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
  const [projects, setProjects] = useState<Project[]>([])
  const [graphs, setGraphs] = useState<Graph[]>([])
  const [loading, setLoading] = useState(true)
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [flowToDelete, setFlowToDelete] = useState<Graph | null>(null)
  const navigate = useNavigate()

  const loadData = useCallback(async () => {
    try {
      setLoading(true)
      const [projectsData, graphsData] = await Promise.all([listProjects(), listGraphs()])
      setProjects(projectsData)
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

  const handleProjectChange = async (graph: Graph, newProjectId: number) => {
    try {
      const updateData: GraphCreate = {
        name: graph.name,
        project_id: newProjectId,
        spec: graph.spec,
      }
      const updated = await updateGraph(graph.id, updateData)
      if (newProjectId !== projectId) {
        setGraphs((prev) => prev.filter((g) => g.id !== graph.id))
      } else {
        setGraphs((prev) => prev.map((g) => (g.id === graph.id ? updated : g)))
      }
      onDataChanged?.()
    } catch (error) {
      console.error('Failed to update flow project:', error)
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
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-muted-foreground">
          Flows in this project. Open the editor to change the graph.
        </p>
        <Button
          type="button"
          onClick={() => navigate(`/flow/new?project=${encodeURIComponent(projectSlug)}`)}
        >
          <Plus className="h-4 w-4 mr-2" />
          New flow
        </Button>
      </div>

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
                    <th className="text-left p-3 sm:p-4 font-medium">Project</th>
                    <th className="text-left p-3 sm:p-4 font-medium">Nodes</th>
                    <th className="text-left p-3 sm:p-4 font-medium hidden sm:table-cell">Created</th>
                    <th className="text-right p-3 sm:p-4 font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {graphs.map((graph) => (
                    <tr
                      key={graph.id}
                      className="border-b last:border-b-0 hover:bg-muted/50 transition-colors"
                    >
                      <td
                        className="p-3 sm:p-4 cursor-pointer align-top"
                        onClick={() => navigate(`/flow/${graph.id}/edit`)}
                      >
                        <div className="font-medium">{graph.name}</div>
                      </td>
                      <td
                        className="p-3 sm:p-4 align-top"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <Select
                          value={graph.project_id.toString()}
                          onValueChange={(value) =>
                            handleProjectChange(graph, parseInt(value, 10))
                          }
                        >
                          <SelectTrigger className="w-[min(100%,12rem)]">
                            <SelectValue placeholder="Select project" />
                          </SelectTrigger>
                          <SelectContent>
                            {projects.map((project) => (
                              <SelectItem key={project.id} value={project.id.toString()}>
                                {project.name}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </td>
                      <td
                        className="p-3 sm:p-4 cursor-pointer align-top max-w-[200px] sm:max-w-md"
                        onClick={() => navigate(`/flow/${graph.id}/edit`)}
                      >
                        <div className="flex flex-wrap gap-1">
                          {graph.spec.nodes.map((node) => (
                            <span
                              key={node.id}
                              className="text-xs px-2 py-0.5 bg-secondary rounded-md"
                            >
                              {node.type}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td
                        className="p-3 sm:p-4 text-muted-foreground cursor-pointer align-top hidden sm:table-cell whitespace-nowrap"
                        onClick={() => navigate(`/flow/${graph.id}/edit`)}
                      >
                        {formatDateCentral(graph.created_at, { includeTime: false })}
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
